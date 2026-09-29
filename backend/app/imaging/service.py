import asyncio
import uuid
from pathlib import Path

from PIL.PngImagePlugin import PngInfo
from sqlmodel import Session, select

from ..config import DATA_DIR, abs_data_path, get_settings, rel_data_path
from ..db import engine
from ..jobs import JobContext, manager
from ..models import Character, DialogueGroup, ImageAsset, Location, Project, Scene
from .base import ImageRequest
from ..services.scene_flow import rebuild_prompt
from .prompt_builder import (
    BREAK,
    BuiltPrompt,
    build_background_prompt,
    build_character_test_prompt,
    lora_for,
    ref_paths,
)
from .registry import get_backend


def _project_image_dir(project_id: int | None) -> Path:
    d = DATA_DIR / "projects" / str(project_id or 0) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_target(session: Session, payload: dict) -> tuple[BuiltPrompt, dict]:
    """Returns the prompt bundle and ImageAsset link fields for the job target."""
    settings = get_settings()
    target, target_id = payload["target"], payload["id"]
    if target == "group":
        group = session.get(DialogueGroup, target_id)
        if group is None:
            raise ValueError("Dialogue block no longer exists")
        scene = session.get(Scene, group.scene_id)
        if not group.prompt:
            rebuild_prompt(session, group)
        chars = {c.id: c for c in session.exec(select(Character).where(Character.project_id == scene.project_id))}
        present = [chars[c["id"]] for c in group.shot.get("characters", []) if c.get("id") in chars]
        loras = [l for l in (lora_for(c) for c in present) if l]
        ip_refs = [p for c in present if not lora_for(c) for p in ref_paths(c)]
        built = BuiltPrompt(group.prompt, group.negative_prompt, loras, ip_refs, list(group.warnings))
        return built, {"project_id": scene.project_id, "group_id": group.id, "kind": "scene"}
    if target == "character":
        ch = session.get(Character, target_id)
        project = session.get(Project, ch.project_id)
        built = build_character_test_prompt(
            ch, payload.get("extra", ""), project.style_preset or settings.style_preset, settings.negative_prompt
        )
        return built, {"project_id": ch.project_id, "character_id": ch.id, "kind": "test"}
    if target == "location":
        loc = session.get(Location, target_id)
        project = session.get(Project, loc.project_id)
        built = build_background_prompt(
            loc, payload.get("extra", ""), project.style_preset or settings.style_preset, settings.negative_prompt
        )
        return built, {"project_id": loc.project_id, "location_id": loc.id, "kind": "background"}
    raise ValueError(f"Unknown target {target}")


def _set_group_status(group_id: int, status: str) -> None:
    with Session(engine) as s:
        g = s.get(DialogueGroup, group_id)
        if g:
            g.status = status
            s.add(g)
            s.commit()


@manager.register("generate_images", gpu=True)
async def generate_images_job(ctx: JobContext) -> dict:
    p = ctx.payload
    settings = get_settings()
    with Session(engine) as session:
        built, link = _resolve_target(session, p)
        source = session.get(ImageAsset, p["source_image_id"]) if p.get("source_image_id") else None

    prompt = p.get("prompt") or built.prompt
    negative = p.get("negative_prompt") if p.get("negative_prompt") is not None else built.negative
    width = p.get("width") or (source.width if source else settings.width)
    height = p.get("height") or (source.height if source else settings.height)
    if link["kind"] == "test" and not p.get("width"):
        width, height = 896, 1152

    req = ImageRequest(
        prompt=prompt,
        negative_prompt=negative,
        width=int(width),
        height=int(height),
        steps=int(p.get("steps") or settings.steps),
        cfg=float(p.get("cfg") or settings.cfg),
        seed=int(p.get("seed", -1) if p.get("seed") is not None else -1),
        num_images=max(1, min(8, int(p.get("count") or settings.variants))),
        loras=built.loras,
        mode=p.get("mode", "txt2img"),
        init_image=abs_data_path(source.path) if source and p.get("mode") in ("img2img", "inpaint") else None,
        mask_image=Path(p["mask_path"]) if p.get("mask_path") else None,
        strength=float(p.get("strength", 0.55)),
        ip_adapter_images=built.ip_refs if p.get("use_ip_adapter", True) else [],
        ip_adapter_scale=settings.ip_adapter_scale * (0.75 if BREAK in built.prompt else 1.0),
    )
    req.resolved_seed()
    backend = get_backend()
    ctx.log(f"Backend: {backend.name} | mode={req.mode} | {req.width}x{req.height} | seed={req.seed}")
    ctx.log(f"Prompt: {req.prompt}")
    if req.loras:
        ctx.log("LoRAs: " + ", ".join(f"{l.path.name}@{l.weight}" for l in req.loras))
    if req.ip_adapter_images:
        ctx.log(f"IP-Adapter refs: {len(req.ip_adapter_images)}")

    group_id = link.get("group_id")
    previous_status = None
    if group_id:
        with Session(engine) as session:
            g = session.get(DialogueGroup, group_id)
            previous_status = g.status if g and g.status != "imaging" else "approved"
        _set_group_status(group_id, "imaging")

    def progress(frac: float, msg: str) -> None:
        ctx.update(frac, msg)

    try:
        results = await asyncio.to_thread(backend.generate, req, progress, ctx.cancel_event)
    except BaseException:
        if group_id and previous_status:
            _set_group_status(group_id, previous_status)
        raise

    out_dir = _project_image_dir(link.get("project_id"))
    ids = []
    with Session(engine) as session:
        for res in results:
            path = out_dir / f"{link['kind']}_{uuid.uuid4().hex[:10]}.png"
            info = PngInfo()
            info.add_text("parameters", f"{req.prompt}\nNegative prompt: {req.negative_prompt}\nSeed: {res.seed}")
            res.image.save(path, pnginfo=info)
            asset = ImageAsset(
                **link,
                path=rel_data_path(path),
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                seed=res.seed,
                width=res.image.width,
                height=res.image.height,
                backend=backend.name,
                meta={"mode": req.mode, "steps": req.steps, "cfg": req.cfg, "loras": [l.path.name for l in req.loras]},
            )
            session.add(asset)
            session.commit()
            session.refresh(asset)
            ids.append(asset.id)
        if group_id:
            g = session.get(DialogueGroup, group_id)
            if g:
                g.status = "done" if g.selected_image_id else "images_ready"
                session.add(g)
                session.commit()
        if link["kind"] == "background" and ids:
            loc = session.get(Location, link["location_id"])
            if loc and not loc.image_path:
                loc.image_path = session.get(ImageAsset, ids[0]).path
                session.add(loc)
                session.commit()
    return {"image_ids": ids, **{k: v for k, v in link.items() if k != "kind"}}


async def enqueue(payload: dict, label: str) -> dict:
    job = await manager.submit("generate_images", payload, message=label)
    return {"job_id": job.id}
