import asyncio
import json
import shutil
import sys
from pathlib import Path

from sqlmodel import Session

from ..config import DATA_DIR, ROOT_DIR, abs_data_path, get_settings, rel_data_path
from ..db import engine
from ..imaging.device import INSTALL_HINT, pick_device, torch_available
from ..imaging.diffusers_backend import resolve_checkpoint
from ..imaging.prompt_builder import STYLE_PRESETS
from ..imaging.registry import unload_all
from ..jobs import JobCancelled, JobContext, manager
from ..llm.provider import LLMProvider
from ..models import Character, Project, TrainingRun
from .tagger import tag_image

PRESETS: dict[str, dict] = {
    "fast": {"label": "Fast (800 steps, rank 16)", "steps": 800, "rank": 16, "lr": 1e-4, "resolution": 1024},
    "quality": {"label": "Quality (1600 steps, rank 32)", "steps": 1600, "rank": 32, "lr": 8e-5, "resolution": 1024},
    "light": {"label": "Low memory (600 steps, rank 8, 768px)", "steps": 600, "rank": 8, "lr": 1.2e-4, "resolution": 768},
}

VISION_CAPTION_PROMPT = (
    "Describe this character image as a single line of comma-separated danbooru-style tags: "
    "hair, eyes, clothing, pose, expression, framing, background. Output only the tags."
)


def with_trigger(trigger: str, caption: str) -> str:
    tags = [t.strip() for t in caption.split(",") if t.strip() and t.strip().lower() != trigger.lower()]
    return ", ".join([trigger, *tags]) if trigger else ", ".join(tags)


@manager.register("caption_refs", gpu=False)
async def caption_refs_job(ctx: JobContext) -> dict:
    settings = get_settings()
    cid = ctx.payload["character_id"]
    overwrite = ctx.payload.get("overwrite", False)
    with Session(engine) as s:
        ch = s.get(Character, cid)
        refs = list(ch.ref_images)
        trigger = ch.trigger_word
    todo = [i for i, r in enumerate(refs) if overwrite or not r.get("caption")]
    llm = LLMProvider()
    for n, i in enumerate(todo):
        ctx.check_cancelled()
        path = abs_data_path(refs[i]["file"])
        ctx.update(n / max(1, len(todo)), f"Captioning {n + 1}/{len(todo)}")
        if settings.captioner == "vision_llm":
            caption = await llm.describe_image(path, VISION_CAPTION_PROMPT)
        else:
            tags = await asyncio.to_thread(tag_image, path, settings.wd14_repo, settings.wd14_threshold)
            caption = ", ".join(tags)
        refs[i] = {**refs[i], "caption": with_trigger(trigger, caption.replace("\n", ", "))}
        ctx.log(f"{Path(refs[i]['file']).name}: {refs[i]['caption']}")
        with Session(engine) as s:
            ch = s.get(Character, cid)
            ch.ref_images = list(refs)
            s.add(ch)
            s.commit()
    return {"character_id": cid, "captioned": len(todo)}


def _prepare_dataset(ch: Character, run_dir: Path) -> Path:
    ds = run_dir / "dataset"
    if ds.exists():
        shutil.rmtree(ds)
    ds.mkdir(parents=True)
    fallback = with_trigger(ch.trigger_word, ch.appearance_tags)
    for i, ref in enumerate(ch.ref_images):
        src = abs_data_path(ref["file"])
        if not src.exists():
            continue
        dst = ds / f"{i:03d}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        caption = ref.get("caption") or fallback
        dst.with_suffix(".txt").write_text(with_trigger(ch.trigger_word, caption))
    return ds


def _update_run(run_id: int, **fields) -> None:
    with Session(engine) as s:
        run = s.get(TrainingRun, run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        s.add(run)
        s.commit()


@manager.register("train_lora", gpu=True)
async def train_lora_job(ctx: JobContext) -> dict:
    if not torch_available():
        raise RuntimeError(INSTALL_HINT)
    settings = get_settings()
    run_id = ctx.payload["run_id"]
    with Session(engine) as s:
        run = s.get(TrainingRun, run_id)
        ch = s.get(Character, run.character_id)
        project = s.get(Project, ch.project_id)
        if len(ch.ref_images) < 3:
            raise RuntimeError("Upload at least 3 reference images (5-20 recommended)")
        run_dir = DATA_DIR / "training" / f"run_{run_id}"
        dataset = _prepare_dataset(ch, run_dir)
        params = dict(run.params)
        style = STYLE_PRESETS.get(project.style_preset or settings.style_preset, STYLE_PRESETS["anime_vn"])
        base = f"{style['positive']}, solo, {ch.trigger_word}, {ch.appearance_tags}".strip(", ")
        trigger = ch.trigger_word
        character_id = ch.id
        name = "".join(c if c.isalnum() else "_" for c in trigger or f"char{ch.id}")

    checkpoint = resolve_checkpoint(params.get("checkpoint", ""))
    device = pick_device()
    config = {
        "checkpoint": checkpoint,
        "dataset_dir": str(dataset),
        "output_dir": str(run_dir / "output"),
        "name": name,
        "trigger": trigger,
        "device": device,
        "dtype": settings.dtype if settings.dtype != "auto" else "auto",
        "steps": params["steps"],
        "rank": params["rank"],
        "lr": params["lr"],
        "resolution": params["resolution"],
        "save_every": params.get("save_every") or max(100, params["steps"] // 4),
        "sample_prompts": [
            f"{base}, upper body, looking at viewer, smile, simple background",
            f"{base}, full body, standing, outdoors, city street",
        ],
        "sample_negative": style["negative"],
        "gradient_checkpointing": True,
    }
    cfg_path = run_dir / "config.json"
    cfg_path.write_text(json.dumps(config, indent=2))
    _update_run(run_id, status="running", dataset_dir=rel_data_path(dataset), output_dir=rel_data_path(run_dir / "output"))

    ctx.update(0.0, "Freeing image model memory", force=True)
    await asyncio.to_thread(unload_all)
    ctx.log(f"Training on {device} from {Path(checkpoint).name} | {params}")

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.training.train_sdxl_lora",
        str(cfg_path),
        cwd=str(ROOT_DIR / "backend"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        limit=2**20,
    )
    ctx.on_cancel = lambda: proc.terminate()
    checkpoints: list[dict] = []
    error = ""
    assert proc.stdout
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        if not line.startswith("{"):
            if line.strip():
                ctx.log(line)
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            ctx.log(line)
            continue
        kind = ev.get("event")
        if kind == "status":
            ctx.update(message=ev["message"])
            ctx.log(ev["message"])
        elif kind == "progress":
            eta = ev.get("eta_s", 0)
            ctx.update(
                ev["step"] / ev["total"],
                f"Step {ev['step']}/{ev['total']} - loss {ev['loss']:.4f} - ETA {eta // 60}m{eta % 60:02d}s",
            )
        elif kind == "checkpoint":
            checkpoints.append(
                {
                    "step": ev["step"],
                    "path": rel_data_path(ev["path"]),
                    "samples": [rel_data_path(p) for p in ev.get("samples", [])],
                }
            )
            _update_run(run_id, checkpoints=list(checkpoints))
            ctx.log(f"Saved checkpoint at step {ev['step']}")
        elif kind == "error":
            error = ev.get("message", "training failed")
            ctx.log(ev.get("trace", error))
    code = await proc.wait()
    if ctx.cancelled:
        _update_run(run_id, status="cancelled")
        raise JobCancelled()
    if code != 0 or error:
        _update_run(run_id, status="failed")
        raise RuntimeError(error or f"Trainer exited with code {code}")

    final = checkpoints[-1]["path"] if checkpoints else ""
    _update_run(run_id, status="done")
    with Session(engine) as s:
        ch = s.get(Character, character_id)
        if final and (ctx.payload.get("auto_assign", True) or not ch.lora_path):
            ch.lora_path = final
            s.add(ch)
            s.commit()
    return {"character_id": character_id, "run_id": run_id, "lora": final}
