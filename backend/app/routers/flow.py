import base64
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session

from ..config import DATA_DIR
from ..db import get_session
from ..imaging.service import enqueue
from ..llm import prompts
from ..llm.provider import LLMError, LLMProvider
from ..models import DialogueGroup, ImageAsset, Project, Scene
from ..services import scene_flow
from ..services.crud import apply_update, delete_group, get_or_404, scene_detail

router = APIRouter(prefix="/api", tags=["flow"])


def _scene_of_group(session: Session, group_id: int) -> dict:
    group = get_or_404(session, DialogueGroup, group_id)
    return scene_detail(session, get_or_404(session, Scene, group.scene_id))


async def _llm_call(coro: Any) -> Any:
    try:
        return await coro
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/scenes/{scene_id}/groups/next")
async def next_group(scene_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    await _llm_call(
        scene_flow.generate_next_group(session, scene_id, data.get("guidance", ""), int(data.get("size", 5)))
    )
    return scene_detail(session, get_or_404(session, Scene, scene_id))


@router.post("/groups/{group_id}/regenerate")
async def regenerate_group(group_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    size = data.get("size")
    await _llm_call(
        scene_flow.regenerate_group(session, group_id, data.get("guidance", ""), int(size) if size else None)
    )
    return _scene_of_group(session, group_id)


@router.post("/lines/{line_id}/regenerate")
async def regenerate_line(line_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    line = await _llm_call(scene_flow.regenerate_line(session, line_id, data.get("guidance", "")))
    return _scene_of_group(session, line.group_id)


@router.put("/groups/{group_id}/lines")
def put_lines(group_id: int, lines: list[dict] = Body(...), session: Session = Depends(get_session)) -> dict:
    scene_flow.replace_lines(session, group_id, lines)
    return _scene_of_group(session, group_id)


@router.patch("/groups/{group_id}")
def patch_group(group_id: int, data: dict = Body(...), session: Session = Depends(get_session)) -> dict:
    group = get_or_404(session, DialogueGroup, group_id)
    rebuild = "shot" in data and "prompt" not in data
    apply_update(group, {k: v for k, v in data.items() if k in ("prompt", "negative_prompt", "shot", "guidance")})
    if rebuild:
        scene_flow.rebuild_prompt(session, group)
    session.add(group)
    session.commit()
    return _scene_of_group(session, group_id)


@router.delete("/groups/{group_id}")
def remove_group(group_id: int, session: Session = Depends(get_session)) -> dict:
    group = get_or_404(session, DialogueGroup, group_id)
    scene_id = group.scene_id
    delete_group(session, group)
    session.commit()
    for i, g in enumerate(scene_flow.scene_groups(session, scene_id)):
        g.order = i
        session.add(g)
    session.commit()
    return scene_detail(session, get_or_404(session, Scene, scene_id))


@router.post("/groups/{group_id}/approve")
async def approve(group_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    group = await _llm_call(scene_flow.approve_group(session, group_id))
    if data.get("auto_images", True):
        await enqueue({"target": "group", "id": group.id, "count": data.get("count")}, f"Scene images for block {group.order + 1}")
    return _scene_of_group(session, group_id)


@router.post("/groups/{group_id}/unapprove")
def unapprove(group_id: int, session: Session = Depends(get_session)) -> dict:
    scene_flow.unapprove_group(session, group_id)
    return _scene_of_group(session, group_id)


@router.post("/groups/{group_id}/shot")
async def reshoot(group_id: int, session: Session = Depends(get_session)) -> dict:
    group = get_or_404(session, DialogueGroup, group_id)
    await _llm_call(scene_flow.make_shot(session, group))
    session.add(group)
    session.commit()
    return _scene_of_group(session, group_id)


@router.post("/groups/{group_id}/images")
async def group_images(group_id: int, data: dict = Body(default={}), session: Session = Depends(get_session)) -> dict:
    group = get_or_404(session, DialogueGroup, group_id)
    if group.status == "draft":
        raise HTTPException(400, "Approve the dialogue block before generating images")
    payload: dict[str, Any] = {"target": "group", "id": group_id}
    for key in ("count", "seed", "mode", "source_image_id", "strength", "prompt", "negative_prompt", "steps", "cfg", "use_ip_adapter"):
        if data.get(key) is not None:
            payload[key] = data[key]
    if data.get("mask"):
        payload["mask_path"] = _save_mask(data["mask"])
        payload["mode"] = "inpaint"
    label = {"img2img": "Variation", "inpaint": "Inpaint"}.get(payload.get("mode", ""), "Scene images")
    return await enqueue(payload, f"{label} for block {group.order + 1}")


def _save_mask(data_url: str) -> str:
    b64 = data_url.split(",", 1)[-1]
    path = DATA_DIR / "tmp" / f"mask_{uuid.uuid4().hex[:10]}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(b64))
    return str(path)


@router.post("/groups/{group_id}/select")
def select_image(group_id: int, data: dict = Body(...), session: Session = Depends(get_session)) -> dict:
    group = get_or_404(session, DialogueGroup, group_id)
    image_id = data.get("image_id")
    if image_id is not None:
        img = get_or_404(session, ImageAsset, image_id)
        if img.group_id != group_id:
            raise HTTPException(400, "Image does not belong to this block")
    group.selected_image_id = image_id
    if group.status in ("images_ready", "done"):
        group.status = "done" if image_id else "images_ready"
    session.add(group)
    session.commit()
    return _scene_of_group(session, group_id)


@router.post("/scenes/{scene_id}/complete")
async def complete(scene_id: int, session: Session = Depends(get_session)) -> dict:
    await _llm_call(scene_flow.complete_scene(session, scene_id))
    return scene_detail(session, get_or_404(session, Scene, scene_id))


@router.post("/scenes/{scene_id}/reopen")
def reopen(scene_id: int, session: Session = Depends(get_session)) -> dict:
    scene = get_or_404(session, Scene, scene_id)
    scene.status = "drafting"
    session.add(scene)
    session.commit()
    return scene_detail(session, scene)


@router.post("/projects/{project_id}/characters/expand")
async def expand_character(project_id: int, data: dict = Body(...), session: Session = Depends(get_session)) -> dict:
    project = get_or_404(session, Project, project_id)
    return await _llm_call(
        LLMProvider().chat_json(
            prompts.WRITER_SYSTEM,
            prompts.expand_character_prompt(project, data.get("name", ""), data.get("brief", "")),
            validate=prompts.validate_character,
        )
    )


@router.post("/characters/{character_id}/test-image")
async def character_test_image(character_id: int, data: dict = Body(default={})) -> dict:
    payload = {"target": "character", "id": character_id, "count": data.get("count", 1), "extra": data.get("extra", "")}
    if data.get("seed") is not None:
        payload["seed"] = data["seed"]
    return await enqueue(payload, "Character test image")


@router.post("/locations/{location_id}/background")
async def location_background(location_id: int, data: dict = Body(default={})) -> dict:
    return await enqueue(
        {"target": "location", "id": location_id, "count": data.get("count", 1), "extra": data.get("extra", "")},
        "Background image",
    )
