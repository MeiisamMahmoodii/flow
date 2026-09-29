from typing import Any, TypeVar

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, select

from ..models import (
    Character,
    DialogueGroup,
    DialogueLine,
    ImageAsset,
    Location,
    Scene,
    TrainingRun,
)

T = TypeVar("T", bound=SQLModel)

IMMUTABLE = {"id", "project_id", "scene_id", "group_id", "character_id", "created_at"}


def get_or_404(session: Session, model: type[T], obj_id: int) -> T:
    obj = session.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj


def apply_update(obj: SQLModel, data: dict[str, Any]) -> None:
    for key, value in data.items():
        if key in IMMUTABLE or not hasattr(obj, key):
            continue
        setattr(obj, key, value)


def group_lines(session: Session, group_id: int) -> list[DialogueLine]:
    return list(
        session.exec(
            select(DialogueLine).where(DialogueLine.group_id == group_id).order_by(DialogueLine.order)
        )
    )


def scene_groups(session: Session, scene_id: int) -> list[DialogueGroup]:
    return list(
        session.exec(
            select(DialogueGroup).where(DialogueGroup.scene_id == scene_id).order_by(DialogueGroup.order)
        )
    )


def group_images(session: Session, group_id: int) -> list[ImageAsset]:
    return list(
        session.exec(
            select(ImageAsset).where(ImageAsset.group_id == group_id).order_by(ImageAsset.id.desc())
        )
    )


def delete_group(session: Session, group: DialogueGroup) -> None:
    for line in group_lines(session, group.id):
        session.delete(line)
    for img in group_images(session, group.id):
        session.delete(img)
    session.delete(group)


def delete_scene(session: Session, scene: Scene) -> None:
    for group in scene_groups(session, scene.id):
        delete_group(session, group)
    session.delete(scene)


def delete_character(session: Session, character: Character) -> None:
    for run in session.exec(select(TrainingRun).where(TrainingRun.character_id == character.id)):
        session.delete(run)
    session.delete(character)


def delete_project_tree(session: Session, project_id: int) -> None:
    for scene in session.exec(select(Scene).where(Scene.project_id == project_id)):
        delete_scene(session, scene)
    for ch in session.exec(select(Character).where(Character.project_id == project_id)):
        delete_character(session, ch)
    for loc in session.exec(select(Location).where(Location.project_id == project_id)):
        session.delete(loc)
    for img in session.exec(select(ImageAsset).where(ImageAsset.project_id == project_id)):
        session.delete(img)


def scene_detail(session: Session, scene: Scene) -> dict:
    groups = []
    for g in scene_groups(session, scene.id):
        groups.append(
            {
                **g.model_dump(),
                "lines": [l.model_dump() for l in group_lines(session, g.id)],
                "images": [i.model_dump(mode="json") for i in group_images(session, g.id)],
            }
        )
    return {**scene.model_dump(), "groups": groups}
