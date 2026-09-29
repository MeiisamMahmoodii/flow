"""Standalone SDXL LoRA trainer (CUDA or Apple MPS).

Run as: python -m app.training.train_sdxl_lora <config.json>
Emits one JSON object per line on stdout: status / progress / checkpoint / sample / done / error.
The output LoRA is saved in kohya format so it loads in diffusers, ComfyUI and A1111/Forge alike.
"""

import json
import math
import random
import sys
import time
import traceback
from pathlib import Path

BUCKETS_1024 = [
    (1024, 1024), (896, 1152), (1152, 896), (832, 1216), (1216, 832), (768, 1344), (1344, 768),
]


def emit(event: str, **kw) -> None:
    print(json.dumps({"event": event, **kw}), flush=True)


def pick_bucket(w: int, h: int, resolution: int) -> tuple[int, int]:
    scale = resolution / 1024
    buckets = [(int(bw * scale) // 64 * 64, int(bh * scale) // 64 * 64) for bw, bh in BUCKETS_1024]
    ar = w / h
    return min(buckets, key=lambda b: abs(b[0] / b[1] - ar))


def load_image(path: Path, size: tuple[int, int]):
    from PIL import Image

    img = Image.open(path).convert("RGB")
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))


def load_dataset(dataset_dir: Path) -> list[tuple[Path, str]]:
    items = []
    for p in sorted(dataset_dir.iterdir()):
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            cap = p.with_suffix(".txt")
            items.append((p, cap.read_text().strip() if cap.exists() else ""))
    if not items:
        raise RuntimeError(f"No training images in {dataset_dir}")
    return items


def main(cfg: dict) -> None:
    import numpy as np
    import torch
    import torch.nn.functional as F
    from diffusers import DDPMScheduler, StableDiffusionXLPipeline
    from diffusers.utils import convert_state_dict_to_kohya
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict
    from PIL import Image
    from safetensors.torch import save_file

    device = cfg["device"]
    dtype_name = cfg.get("dtype", "auto")
    if dtype_name == "auto":
        # bf16 halves memory on Apple Silicon without fp16's overflow-to-NaN issues.
        weight_dtype = {"cuda": torch.float16, "mps": torch.bfloat16}.get(device, torch.float32)
    else:
        weight_dtype = getattr(torch, dtype_name)
    seed = int(cfg.get("seed", 42))
    random.seed(seed)
    torch.manual_seed(seed)

    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    name = cfg["name"]
    rank = int(cfg.get("rank", 16))
    steps = int(cfg.get("steps", 800))
    resolution = int(cfg.get("resolution", 1024))

    emit("status", message="Loading base model")
    ckpt = cfg["checkpoint"]
    if Path(ckpt).is_file():
        pipe = StableDiffusionXLPipeline.from_single_file(ckpt, torch_dtype=weight_dtype)
    else:
        pipe = StableDiffusionXLPipeline.from_pretrained(ckpt, torch_dtype=weight_dtype)
    noise_scheduler = DDPMScheduler.from_config(pipe.scheduler.config)
    prediction_type = noise_scheduler.config.prediction_type
    unet, vae = pipe.unet, pipe.vae
    for m in (unet, vae, pipe.text_encoder, pipe.text_encoder_2):
        m.requires_grad_(False)

    # ---- cache latents + text embeddings, then free the encoders from the device ----
    items = load_dataset(Path(cfg["dataset_dir"]))
    emit("status", message=f"Caching {len(items)} images")
    vae.to(device, dtype=torch.float32)
    pipe.text_encoder.to(device)
    pipe.text_encoder_2.to(device)
    cache = []
    with torch.no_grad():
        for idx, (path, caption) in enumerate(items):
            with Image.open(path) as raw:
                bw, bh = pick_bucket(raw.width, raw.height, resolution)
            img = load_image(path, (bw, bh))
            prompt_embeds, _, pooled, _ = pipe.encode_prompt(
                caption, device=device, num_images_per_prompt=1, do_classifier_free_guidance=False
            )
            variants = [img, img.transpose(Image.FLIP_LEFT_RIGHT)] if cfg.get("flip_aug", True) else [img]
            for v in variants:
                arr = torch.from_numpy(np.asarray(v, dtype=np.float32) / 127.5 - 1.0).permute(2, 0, 1)[None]
                latents = vae.encode(arr.to(device)).latent_dist.sample() * vae.config.scaling_factor
                cache.append(
                    {
                        "latents": latents.cpu(),
                        "embeds": prompt_embeds.cpu(),
                        "pooled": pooled.cpu(),
                        "time_ids": torch.tensor([[bh, bw, 0, 0, bh, bw]], dtype=torch.float32),
                    }
                )
            emit("status", message=f"Cached {idx + 1}/{len(items)}")
    if cfg.get("sample_prompts"):
        vae.to("cpu")
        pipe.text_encoder.to("cpu")
        pipe.text_encoder_2.to("cpu")
    else:
        pipe.vae = pipe.text_encoder = pipe.text_encoder_2 = vae = None
    _free(device)
    emit("status", message=f"Cached dataset ({_mem(device)})")

    # ---- LoRA setup ----
    unet.add_adapter(
        LoraConfig(
            r=rank,
            lora_alpha=rank,
            init_lora_weights="gaussian",
            target_modules=["to_k", "to_q", "to_v", "to_out.0"],
        )
    )
    unet.to(device)
    for p in unet.parameters():
        if p.requires_grad:
            p.data = p.data.to(torch.float32)
    if cfg.get("gradient_checkpointing", True):
        unet.enable_gradient_checkpointing()
    params = [p for p in unet.parameters() if p.requires_grad]
    lr = float(cfg.get("lr", 1e-4))
    optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=1e-2)
    warmup = max(1, int(steps * 0.05))

    def lr_lambda(step: int) -> float:
        if step < warmup:
            return (step + 1) / warmup
        progress = (step - warmup) / max(1, steps - warmup)
        return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
    use_autocast = weight_dtype != torch.float32
    scaler = torch.amp.GradScaler("cuda") if (device == "cuda" and weight_dtype == torch.float16) else None
    noise_offset = float(cfg.get("noise_offset", 0.0357))

    def save_checkpoint(step: int) -> Path:
        sd = get_peft_model_state_dict(unet)
        sd = {f"unet.{k}": v.detach().to("cpu", torch.float16).contiguous() for k, v in sd.items()}
        kohya = convert_state_dict_to_kohya(sd)
        path = out_dir / f"{name}-step{step:05d}.safetensors"
        save_file(
            kohya,
            str(path),
            metadata={
                "ss_network_dim": str(rank),
                "ss_network_alpha": str(rank),
                "ss_base_model": Path(ckpt).name,
                "vnflow_trigger": cfg.get("trigger", ""),
            },
        )
        return path

    def make_samples(step: int) -> list[str]:
        prompts = cfg.get("sample_prompts") or []
        if not prompts:
            return []
        unet.eval()
        pipe.text_encoder.to(device)
        pipe.text_encoder_2.to(device)
        vae.to(device, dtype=torch.float32)
        paths = []
        try:
            with torch.no_grad():
                for i, prompt in enumerate(prompts):
                    embeds = pipe.encode_prompt(prompt, device=device, num_images_per_prompt=1, do_classifier_free_guidance=True, negative_prompt=cfg.get("sample_negative", ""))
                    pe, ne, pp, npp = embeds
                    ctx = torch.autocast(device_type=device, dtype=weight_dtype) if use_autocast else _null()
                    with ctx:
                        latents = _sample_latents(unet, pipe.scheduler, pe, ne, pp, npp, resolution, device, seed + i)
                    image = vae.decode(latents.to(torch.float32) / vae.config.scaling_factor).sample
                    image = ((image[0].clamp(-1, 1) + 1) * 127.5).permute(1, 2, 0).cpu().numpy().astype("uint8")
                    p = out_dir / f"sample-step{step:05d}-{i}.png"
                    Image.fromarray(image).save(p)
                    paths.append(str(p))
        finally:
            pipe.text_encoder.to("cpu")
            pipe.text_encoder_2.to("cpu")
            vae.to("cpu")
            _free(device)
            unet.train()
        return paths

    save_every = int(cfg.get("save_every", max(100, steps // 4)))
    emit("status", message="Training")
    unet.train()
    t0 = time.time()
    ema_loss = None
    for step in range(1, steps + 1):
        item = random.choice(cache)
        latents = item["latents"].to(device, dtype=torch.float32)
        noise = torch.randn_like(latents)
        if noise_offset:
            noise += noise_offset * torch.randn((latents.shape[0], latents.shape[1], 1, 1), device=device)
        t = torch.randint(0, noise_scheduler.config.num_train_timesteps, (1,), device=device).long()
        noisy = noise_scheduler.add_noise(latents, noise, t)
        ctx = torch.autocast(device_type=device, dtype=weight_dtype) if use_autocast else _null()
        with ctx:
            pred = unet(
                noisy.to(weight_dtype),
                t,
                encoder_hidden_states=item["embeds"].to(device, dtype=weight_dtype),
                added_cond_kwargs={
                    "text_embeds": item["pooled"].to(device, dtype=weight_dtype),
                    "time_ids": item["time_ids"].to(device, dtype=weight_dtype),
                },
            ).sample
        target = noise if prediction_type == "epsilon" else noise_scheduler.get_velocity(latents, noise, t)
        loss = F.mse_loss(pred.float(), target.float())
        if scaler:
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        scheduler.step()

        lv = float(loss.detach().item())
        if math.isnan(lv):
            raise RuntimeError("Loss became NaN - try dtype float32 or a lower learning rate")
        ema_loss = lv if ema_loss is None else 0.95 * ema_loss + 0.05 * lv
        elapsed = time.time() - t0
        if step == 1:
            emit("status", message=f"Training ({_mem(device)})")
        emit(
            "progress",
            step=step,
            total=steps,
            loss=round(ema_loss, 5),
            lr=scheduler.get_last_lr()[0],
            eta_s=int(elapsed / step * (steps - step)),
        )
        if step % save_every == 0 or step == steps:
            path = save_checkpoint(step)
            samples = make_samples(step)
            emit("checkpoint", step=step, path=str(path), samples=samples)
    emit("done", path=str(out_dir / f"{name}-step{steps:05d}.safetensors"))


def _free(device: str) -> None:
    import gc

    import torch

    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
    elif device == "mps":
        torch.mps.empty_cache()


def _mem(device: str) -> str:
    import torch

    if device == "cuda":
        return f"{torch.cuda.max_memory_allocated() / 2**30:.1f} GB VRAM peak"
    if device == "mps":
        return f"{torch.mps.driver_allocated_memory() / 2**30:.1f} GB GPU memory"
    return "cpu"


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _sample_latents(unet, base_scheduler, pe, ne, pp, npp, resolution, device, seed, steps=20, cfg=6.0):
    import torch
    from diffusers import EulerDiscreteScheduler

    sched = EulerDiscreteScheduler.from_config(base_scheduler.config)
    sched.set_timesteps(steps, device=device)
    gen = torch.Generator("cpu").manual_seed(seed)
    h = w = resolution
    latents = torch.randn((1, 4, h // 8, w // 8), generator=gen).to(device) * sched.init_noise_sigma
    time_ids = torch.tensor([[h, w, 0, 0, h, w]] * 2, device=device, dtype=pe.dtype)
    embeds = torch.cat([ne, pe])
    pooled = torch.cat([npp, pp])
    for t in sched.timesteps:
        inp = sched.scale_model_input(torch.cat([latents] * 2), t)
        noise = unet(inp.to(pe.dtype), t, encoder_hidden_states=embeds, added_cond_kwargs={"text_embeds": pooled, "time_ids": time_ids}).sample
        uncond, cond = noise.chunk(2)
        latents = sched.step(uncond + cfg * (cond - uncond), t, latents).prev_sample
    return latents


if __name__ == "__main__":
    try:
        main(json.loads(Path(sys.argv[1]).read_text()))
    except Exception as exc:
        emit("error", message=str(exc), trace=traceback.format_exc())
        sys.exit(1)
