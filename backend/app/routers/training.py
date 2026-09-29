import shutil

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from ..config import DATA_DIR
from ..db import get_session
from ..jobs import manager
from ..models import Character, TrainingRun
from ..services.crud import get_or_404
from ..training.jobs import PRESETS

router = APIRouter(prefix="/api", tags=["training"])


@router.get("/training/presets")
def presets() -> dict:
    return PRESETS


@router.post("/characters/{character_id}/caption")
async def caption(character_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    ch = get_or_404(session, Character, character_id)
    if not ch.ref_images:
        raise HTTPException(400, "Upload reference images first")
    job = await manager.submit(
        "caption_refs", {"character_id": character_id, "overwrite": bool(data.get("overwrite"))}, f"Caption {ch.name}"
    )
    return {"job_id": job.id}


@router.post("/characters/{character_id}/train")
async def train(character_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    ch = get_or_404(session, Character, character_id)
    if len(ch.ref_images) < 3:
        raise HTTPException(400, "Upload at least 3 reference images (5-20 recommended)")
    preset_name = data.get("preset", "fast")
    preset = PRESETS.get(preset_name, PRESETS["fast"])
    params = {k: preset[k] for k in ("steps", "rank", "lr", "resolution")}
    for key, cast in (("steps", int), ("rank", int), ("lr", float), ("resolution", int), ("save_every", int)):
        if data.get(key):
            params[key] = cast(data[key])
    if data.get("checkpoint"):
        params["checkpoint"] = data["checkpoint"]
    run = TrainingRun(character_id=character_id, preset=preset_name, params=params)
    session.add(run)
    session.commit()
    session.refresh(run)
    job = await manager.submit(
        "train_lora",
        {"run_id": run.id, "auto_assign": data.get("auto_assign", True)},
        f"Train LoRA for {ch.name}",
    )
    run.job_id = job.id
    session.add(run)
    session.commit()
    return {"job_id": job.id, "run_id": run.id}


@router.get("/characters/{character_id}/training-runs")
def runs(character_id: int, session: Session = Depends(get_session)) -> list[TrainingRun]:
    return list(
        session.exec(
            select(TrainingRun).where(TrainingRun.character_id == character_id).order_by(TrainingRun.id.desc())
        )
    )


@router.post("/training-runs/{run_id}/use")
def use_checkpoint(run_id: int, data: dict = Body(...), session: Session = Depends(get_session)) -> Character:
    run = get_or_404(session, TrainingRun, run_id)
    match = next((c for c in run.checkpoints if c["step"] == data.get("step")), None)
    if not match:
        raise HTTPException(404, "Checkpoint not found in this run")
    ch = get_or_404(session, Character, run.character_id)
    ch.lora_path = match["path"]
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.delete("/training-runs/{run_id}")
def delete_run(run_id: int, session: Session = Depends(get_session)) -> dict:
    run = get_or_404(session, TrainingRun, run_id)
    if run.status in ("queued", "running"):
        raise HTTPException(400, "Cancel the training job first")
    ch = session.get(Character, run.character_id)
    if ch and any(ch.lora_path == c["path"] for c in run.checkpoints):
        ch.lora_path = ""
        session.add(ch)
    session.delete(run)
    session.commit()
    shutil.rmtree(DATA_DIR / "training" / f"run_{run_id}", ignore_errors=True)
    return {"ok": True}
