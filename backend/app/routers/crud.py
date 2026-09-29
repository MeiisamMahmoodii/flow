import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import DATA_DIR, abs_data_path, rel_data_path
from ..db import get_session
from ..models import Character, ImageAsset, Location, Project, Scene
from ..services.crud import (
    apply_update,
    delete_character,
    delete_project_tree,
    delete_scene,
    get_or_404,
    scene_detail,
)

router = APIRouter(prefix="/api", tags=["crud"])

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
CHARACTER_COLORS = ["#c084fc", "#f472b6", "#60a5fa", "#34d399", "#fbbf24", "#f87171", "#22d3ee", "#a3e635"]


def _save_upload(upload: UploadFile, dest_dir: Path, allowed: set[str]) -> Path:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type {ext}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex[:12]}{ext}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    return dest


# ---------- projects ----------


@router.get("/projects")
def list_projects(session: Session = Depends(get_session)) -> list[Project]:
    return list(session.exec(select(Project).order_by(Project.created_at.desc())))


@router.post("/projects")
def create_project(data: dict[str, Any] = Body(...), session: Session = Depends(get_session)) -> Project:
    if not data.get("name"):
        raise HTTPException(400, "name is required")
    project = Project(name=data["name"])
    apply_update(project, data)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("/projects/{project_id}")
def get_project(project_id: int, session: Session = Depends(get_session)) -> dict:
    project = get_or_404(session, Project, project_id)
    return {
        **project.model_dump(mode="json"),
        "characters": list(session.exec(select(Character).where(Character.project_id == project_id))),
        "locations": list(session.exec(select(Location).where(Location.project_id == project_id))),
        "scenes": list(
            session.exec(select(Scene).where(Scene.project_id == project_id).order_by(Scene.order, Scene.id))
        ),
    }


@router.patch("/projects/{project_id}")
def update_project(
    project_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Project:
    project = get_or_404(session, Project, project_id)
    apply_update(project, data)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: int, session: Session = Depends(get_session)) -> dict:
    project = get_or_404(session, Project, project_id)
    delete_project_tree(session, project_id)
    session.delete(project)
    session.commit()
    shutil.rmtree(DATA_DIR / "projects" / str(project_id), ignore_errors=True)
    return {"ok": True}


# ---------- characters ----------


@router.post("/projects/{project_id}/characters")
def create_character(
    project_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Character:
    get_or_404(session, Project, project_id)
    if not data.get("name"):
        raise HTTPException(400, "name is required")
    existing = len(list(session.exec(select(Character.id).where(Character.project_id == project_id))))
    ch = Character(project_id=project_id, name=data["name"], color=CHARACTER_COLORS[existing % len(CHARACTER_COLORS)])
    apply_update(ch, data)
    if not ch.trigger_word:
        ch.trigger_word = "".join(c for c in ch.name.lower() if c.isalnum()) + "_vn"
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.get("/characters/{character_id}")
def get_character(character_id: int, session: Session = Depends(get_session)) -> Character:
    return get_or_404(session, Character, character_id)


@router.patch("/characters/{character_id}")
def update_character(
    character_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Character:
    ch = get_or_404(session, Character, character_id)
    apply_update(ch, data)
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.delete("/characters/{character_id}")
def remove_character(character_id: int, session: Session = Depends(get_session)) -> dict:
    ch = get_or_404(session, Character, character_id)
    delete_character(session, ch)
    session.commit()
    return {"ok": True}


@router.post("/characters/{character_id}/refs")
def upload_refs(
    character_id: int,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> Character:
    ch = get_or_404(session, Character, character_id)
    dest_dir = DATA_DIR / "characters" / str(character_id) / "refs"
    refs = list(ch.ref_images)
    for f in files:
        path = _save_upload(f, dest_dir, IMAGE_EXTS)
        refs.append({"file": rel_data_path(path), "caption": ""})
    ch.ref_images = refs
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.patch("/characters/{character_id}/refs")
def update_refs(
    character_id: int, refs: list[dict] = Body(...), session: Session = Depends(get_session)
) -> Character:
    """Replace the ref list (used for caption edits, reordering and deletions)."""
    ch = get_or_404(session, Character, character_id)
    keep = {r["file"] for r in refs}
    for old in ch.ref_images:
        if old["file"] not in keep:
            abs_data_path(old["file"]).unlink(missing_ok=True)
    ch.ref_images = [{"file": r["file"], "caption": r.get("caption", "")} for r in refs]
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@router.post("/characters/{character_id}/lora")
def import_lora(
    character_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)
) -> Character:
    ch = get_or_404(session, Character, character_id)
    path = _save_upload(file, DATA_DIR / "loras", {".safetensors"})
    ch.lora_path = rel_data_path(path)
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


# ---------- locations ----------


@router.post("/projects/{project_id}/locations")
def create_location(
    project_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Location:
    get_or_404(session, Project, project_id)
    if not data.get("name"):
        raise HTTPException(400, "name is required")
    loc = Location(project_id=project_id, name=data["name"])
    apply_update(loc, data)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return loc


@router.patch("/locations/{location_id}")
def update_location(
    location_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Location:
    loc = get_or_404(session, Location, location_id)
    apply_update(loc, data)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return loc


@router.delete("/locations/{location_id}")
def delete_location(location_id: int, session: Session = Depends(get_session)) -> dict:
    loc = get_or_404(session, Location, location_id)
    for scene in session.exec(select(Scene).where(Scene.location_id == location_id)):
        scene.location_id = None
        session.add(scene)
    session.delete(loc)
    session.commit()
    return {"ok": True}


@router.get("/locations/{location_id}/images")
def location_images(location_id: int, session: Session = Depends(get_session)) -> list[ImageAsset]:
    return list(
        session.exec(
            select(ImageAsset).where(ImageAsset.location_id == location_id).order_by(ImageAsset.id.desc())
        )
    )


# ---------- scenes ----------


@router.post("/projects/{project_id}/scenes")
def create_scene(
    project_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Scene:
    get_or_404(session, Project, project_id)
    if not data.get("title"):
        raise HTTPException(400, "title is required")
    count = len(list(session.exec(select(Scene.id).where(Scene.project_id == project_id))))
    scene = Scene(project_id=project_id, title=data["title"], order=count)
    apply_update(scene, data)
    session.add(scene)
    session.commit()
    session.refresh(scene)
    return scene


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: int, session: Session = Depends(get_session)) -> dict:
    return scene_detail(session, get_or_404(session, Scene, scene_id))


@router.patch("/scenes/{scene_id}")
def update_scene(
    scene_id: int, data: dict[str, Any] = Body(...), session: Session = Depends(get_session)
) -> Scene:
    scene = get_or_404(session, Scene, scene_id)
    apply_update(scene, data)
    session.add(scene)
    session.commit()
    session.refresh(scene)
    return scene


@router.delete("/scenes/{scene_id}")
def remove_scene(scene_id: int, session: Session = Depends(get_session)) -> dict:
    scene = get_or_404(session, Scene, scene_id)
    delete_scene(session, scene)
    session.commit()
    return {"ok": True}


# ---------- images ----------


@router.get("/characters/{character_id}/images")
def character_images(character_id: int, session: Session = Depends(get_session)) -> list[ImageAsset]:
    return list(
        session.exec(
            select(ImageAsset).where(ImageAsset.character_id == character_id).order_by(ImageAsset.id.desc())
        )
    )


@router.delete("/images/{image_id}")
def delete_image(image_id: int, session: Session = Depends(get_session)) -> dict:
    img = get_or_404(session, ImageAsset, image_id)
    if img.path:
        abs_data_path(img.path).unlink(missing_ok=True)
    session.delete(img)
    session.commit()
    return {"ok": True}
