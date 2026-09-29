from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_list() -> Any:
    return Field(default_factory=list, sa_column=Column(JSON))


def json_dict() -> Any:
    return Field(default_factory=dict, sa_column=Column(JSON))


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    premise: str = ""
    style_preset: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Character(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str
    description: str = ""
    personality: str = ""
    speech_style: str = ""
    appearance: str = ""
    appearance_tags: str = ""
    relationships: str = ""
    color: str = "#c084fc"
    trigger_word: str = ""
    lora_path: str = ""
    lora_weight: float = 0.8
    # [{"file": rel_path, "caption": str}]
    ref_images: list[dict] = json_list()


class Location(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str
    description: str = ""
    tags: str = ""
    image_path: str = ""


class Scene(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    title: str
    order: int = 0
    location_id: Optional[int] = Field(default=None, foreign_key="location.id")
    cast_ids: list[int] = json_list()
    goal: str = ""
    outline: str = ""
    status: str = "drafting"  # drafting | complete
    summary: str = ""
    llm_suggests_complete: bool = False


class DialogueGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    scene_id: int = Field(foreign_key="scene.id", index=True)
    order: int = 0
    # draft -> approved -> imaging -> images_ready -> done
    status: str = "draft"
    guidance: str = ""
    shot: dict = json_dict()
    prompt: str = ""
    negative_prompt: str = ""
    warnings: list[str] = json_list()
    selected_image_id: Optional[int] = None


class DialogueLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="dialoguegroup.id", index=True)
    order: int = 0
    speaker_id: Optional[int] = None  # None = narrator
    speaker_name: str = "Narrator"
    text: str = ""
    emotion: str = ""
    action: str = ""


class ImageAsset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, index=True)
    group_id: Optional[int] = Field(default=None, index=True)
    character_id: Optional[int] = Field(default=None, index=True)
    location_id: Optional[int] = Field(default=None, index=True)
    kind: str = "scene"  # scene | test | background | sample
    path: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    seed: int = 0
    width: int = 0
    height: int = 0
    backend: str = ""
    meta: dict = json_dict()
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str
    status: str = "queued"  # queued | running | done | failed | cancelled
    progress: float = 0.0
    message: str = ""
    payload: dict = json_dict()
    result: dict = json_dict()
    error: str = ""
    logs: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None


class TrainingRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    character_id: int = Field(foreign_key="character.id", index=True)
    job_id: Optional[int] = None
    status: str = "queued"
    preset: str = "fast"
    params: dict = json_dict()
    dataset_dir: str = ""
    output_dir: str = ""
    # [{"step": int, "path": rel, "samples": [rel]}]
    checkpoints: list[dict] = json_list()
    created_at: datetime = Field(default_factory=utcnow)
