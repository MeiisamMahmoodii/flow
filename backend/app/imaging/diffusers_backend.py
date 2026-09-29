"""Runs SDXL-family checkpoints (SDXL, Illustrious, Pony, NoobAI...) directly with diffusers."""

import gc
import logging
import re
import threading
from pathlib import Path

from PIL import Image

from ..config import get_settings
from .base import GeneratedImage, GenerationCancelled, ImageRequest, LoraSpec, ProgressFn
from .device import INSTALL_HINT, pick_device, pick_dtype, torch_available

log = logging.getLogger("vnflow.diffusers")

MODEL_EXTS = (".safetensors", ".ckpt")


def resolve_checkpoint(name: str) -> str:
    settings = get_settings()
    ckpt_dir = Path(settings.checkpoint_dir).expanduser()
    name = name or settings.default_checkpoint
    if not name:
        found = list_checkpoints()
        if not found:
            raise RuntimeError(
                f"No checkpoint configured. Put an SDXL .safetensors file in {ckpt_dir} "
                "or set a Hugging Face repo id as the default checkpoint in Settings."
            )
        name = found[0]
    p = Path(name).expanduser()
    if not p.is_absolute():
        p = ckpt_dir / name
    if p.exists():
        return str(p)
    if "/" in name and not name.endswith(MODEL_EXTS):
        return name  # Hugging Face repo id
    raise RuntimeError(f"Checkpoint not found: {name}")


def list_checkpoints() -> list[str]:
    ckpt_dir = Path(get_settings().checkpoint_dir).expanduser()
    if not ckpt_dir.exists():
        return []
    out = []
    for p in sorted(ckpt_dir.rglob("*")):
        if p.is_file() and p.suffix in MODEL_EXTS:
            out.append(p.relative_to(ckpt_dir).as_posix())
        elif p.is_dir() and (p / "model_index.json").exists():
            out.append(p.relative_to(ckpt_dir).as_posix())
    return out


def encode_long_prompt(pipe, prompt: str, negative: str, device: str):
    """SDXL prompt encoding without the 77-token limit: 75-token chunks encoded separately and concatenated."""
    import torch

    tokenizers = [pipe.tokenizer, pipe.tokenizer_2]
    encoders = [pipe.text_encoder, pipe.text_encoder_2]

    def token_chunks(tok, text: str) -> list[list[int]]:
        chunks: list[list[int]] = []
        # "BREAK" forces a new chunk (A1111 convention) so segments don't share CLIP context.
        for segment in re.split(r"\s*\bBREAK\b\s*,?", text):
            ids = tok(segment.strip(" ,"), truncation=False, add_special_tokens=False).input_ids
            chunks += [ids[i : i + 75] for i in range(0, len(ids), 75)]
        return chunks or [[]]

    per_tok = [(token_chunks(t, prompt), token_chunks(t, negative)) for t in tokenizers]
    n_chunks = max(len(c) for pair in per_tok for c in pair)

    def encode(which: int):
        hidden_by_encoder = []
        pooled = None
        for (tok, enc), pair in zip(zip(tokenizers, encoders), per_tok):
            chunks = pair[which] + [[]] * (n_chunks - len(pair[which]))
            pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
            states = []
            for i, chunk in enumerate(chunks):
                ids = [tok.bos_token_id] + chunk + [tok.eos_token_id]
                ids += [pad] * (77 - len(ids))
                out = enc(torch.tensor([ids], device=device), output_hidden_states=True)
                states.append(out.hidden_states[-2])
                if enc is pipe.text_encoder_2 and i == 0:
                    pooled = out[0]
            hidden_by_encoder.append(torch.cat(states, dim=1))
        return torch.cat(hidden_by_encoder, dim=-1), pooled

    with torch.no_grad():
        pos, pos_pooled = encode(0)
        neg, neg_pooled = encode(1)
    dtype = pipe.unet.dtype
    return {
        "prompt_embeds": pos.to(dtype),
        "pooled_prompt_embeds": pos_pooled.to(dtype),
        "negative_prompt_embeds": neg.to(dtype),
        "negative_pooled_prompt_embeds": neg_pooled.to(dtype),
    }


class DiffusersBackend:
    name = "diffusers"
    supports_lora = True
    supports_ip_adapter = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pipe = None
        self._ckpt: str | None = None
        self._device: str | None = None
        self._lora_key: tuple = ()
        self._ip_loaded = False
        self._ip_key: tuple = ()

    # ---------- lifecycle ----------

    def status(self) -> dict:
        return {
            "backend": self.name,
            "available": torch_available(),
            "loaded_checkpoint": self._ckpt,
            "device": self._device,
            "ip_adapter_loaded": self._ip_loaded,
            "hint": None if torch_available() else INSTALL_HINT,
        }

    def list_models(self) -> list[str]:
        return list_checkpoints()

    def unload(self) -> None:
        with self._lock:
            self._release()

    def _release(self) -> None:
        self._pipe = None
        self._ckpt = None
        self._lora_key = ()
        self._ip_loaded = False
        gc.collect()
        if torch_available():
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                torch.mps.empty_cache()

    def _ensure_pipe(self, checkpoint: str, progress: ProgressFn):
        if not torch_available():
            raise RuntimeError(INSTALL_HINT)
        ckpt = resolve_checkpoint(checkpoint)
        if self._pipe is not None and self._ckpt == ckpt:
            return self._pipe
        self._release()
        progress(0.0, f"Loading checkpoint {Path(ckpt).name} (first load can take a while)")
        from diffusers import AutoPipelineForText2Image, EulerAncestralDiscreteScheduler, StableDiffusionXLPipeline

        device = pick_device()
        dtype = pick_dtype(device)
        if Path(ckpt).is_file():
            pipe = StableDiffusionXLPipeline.from_single_file(
                ckpt, torch_dtype=dtype, use_safetensors=ckpt.endswith(".safetensors")
            )
        else:
            pipe = AutoPipelineForText2Image.from_pretrained(ckpt, torch_dtype=dtype)
        if isinstance(pipe, StableDiffusionXLPipeline):
            pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
        pipe.to(device)
        if device == "mps":
            pipe.enable_attention_slicing()
        if hasattr(pipe, "enable_vae_tiling"):
            pipe.enable_vae_tiling()
        pipe.set_progress_bar_config(disable=True)
        self._pipe, self._ckpt, self._device = pipe, ckpt, device
        return pipe

    # ---------- adapters ----------

    def _apply_loras(self, pipe, loras: list[LoraSpec]) -> None:
        key = tuple(str(l.path) for l in loras)
        if key != self._lora_key:
            if self._lora_key:
                pipe.unload_lora_weights()
            for l in loras:
                pipe.load_lora_weights(str(l.path.parent), weight_name=l.path.name, adapter_name=l.name)
            self._lora_key = key
        if loras:
            pipe.set_adapters([l.name for l in loras], adapter_weights=[l.weight for l in loras])

    def _apply_ip_adapter(self, pipe, needed: bool, scale: float) -> None:
        s = get_settings()
        key = (s.ip_adapter_repo, s.ip_adapter_subfolder, s.ip_adapter_weight, s.ip_adapter_image_encoder)
        if needed and self._ip_loaded and key != self._ip_key:
            pipe.unload_ip_adapter()
            self._ip_loaded = False
        if needed and not self._ip_loaded:
            # IP-Adapter attention processors can't be built on top of sliced attention.
            pipe.disable_attention_slicing()
            pipe.load_ip_adapter(
                s.ip_adapter_repo,
                subfolder=s.ip_adapter_subfolder,
                weight_name=s.ip_adapter_weight,
                image_encoder_folder=s.ip_adapter_image_encoder or None,
            )
            self._ip_loaded = True
            self._ip_key = key
        elif not needed and self._ip_loaded:
            pipe.unload_ip_adapter()
            self._ip_loaded = False
            if self._device == "mps":
                pipe.enable_attention_slicing()
        if needed:
            pipe.set_ip_adapter_scale(scale)

    # ---------- generation ----------

    def generate(self, req: ImageRequest, progress: ProgressFn, cancel: threading.Event) -> list[GeneratedImage]:
        import torch
        from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLInpaintPipeline

        with self._lock:
            base = self._ensure_pipe(req.checkpoint, progress)
            is_sdxl = hasattr(base, "tokenizer_2") and base.tokenizer_2 is not None
            use_ip = bool(req.ip_adapter_images)
            try:
                if req.loras:
                    progress(0.0, "Loading LoRAs")
                self._apply_loras(base, req.loras)
                if use_ip:
                    progress(0.0, "Loading IP-Adapter")
                self._apply_ip_adapter(base, use_ip, req.ip_adapter_scale)
            except Exception:
                # A half-applied adapter leaves the cached pipeline in an unknown state.
                self._release()
                raise

            pipe = base
            extra: dict = {}
            if req.mode in ("img2img", "inpaint"):
                if not req.init_image:
                    raise ValueError(f"{req.mode} requires a source image")
                init = Image.open(req.init_image).convert("RGB").resize((req.width, req.height))
                extra["image"] = init
                extra["strength"] = req.strength
                if req.mode == "inpaint":
                    if not req.mask_image:
                        raise ValueError("inpaint requires a mask")
                    pipe = StableDiffusionXLInpaintPipeline.from_pipe(base)
                    extra["mask_image"] = Image.open(req.mask_image).convert("L").resize((req.width, req.height))
                    extra["strength"] = max(req.strength, 0.75)
                else:
                    pipe = StableDiffusionXLImg2ImgPipeline.from_pipe(base)
                pipe.set_progress_bar_config(disable=True)

            if use_ip:
                refs = [Image.open(p).convert("RGB") for p in req.ip_adapter_images[:4]]
                extra["ip_adapter_image"] = [refs]

            if is_sdxl:
                extra.update(encode_long_prompt(base, req.prompt, req.negative_prompt, self._device))
            else:
                extra["prompt"] = re.sub(r"\s*\bBREAK\b\s*", ", ", req.prompt)
                extra["negative_prompt"] = req.negative_prompt or None

            total = req.num_images
            effective_steps = req.steps if req.mode == "txt2img" else max(1, int(req.steps * extra["strength"]))
            results: list[GeneratedImage] = []
            for i in range(total):
                seed = req.seed + i
                idx = i

                def on_step(p, step, timestep, kwargs, idx=idx):
                    if cancel.is_set():
                        p._interrupt = True
                    frac = (idx + (step + 1) / effective_steps) / total
                    progress(min(frac, 0.99), f"Image {idx + 1}/{total} - step {step + 1}/{effective_steps}")
                    return kwargs

                out = pipe(
                    num_inference_steps=req.steps,
                    guidance_scale=req.cfg,
                    width=req.width,
                    height=req.height,
                    generator=torch.Generator(device="cpu").manual_seed(seed),
                    callback_on_step_end=on_step,
                    **extra,
                )
                if cancel.is_set():
                    raise GenerationCancelled()
                results.append(GeneratedImage(image=out.images[0], seed=seed))
            return results
