"""Dialogue-first scene building state machine.

draft --approve--> approved (shot + prompt ready) --images--> imaging --> images_ready --select--> done
Any approved group can be sent back to draft with `unapprove`.
"""

from fastapi import HTTPException
from sqlmodel import Session, select

from ..config import get_settings
from ..imaging.prompt_builder import STYLE_PRESETS, build_scene_prompt
from ..llm import prompts
from ..llm.provider import LLMProvider
from ..models import Character, DialogueGroup, DialogueLine, Location, Project, Scene
from .crud import get_or_404, group_lines, scene_groups

DRAFT = "draft"
APPROVED_STATES = {"approved", "imaging", "images_ready", "done"}


class SceneContext:
    def __init__(self, session: Session, scene: Scene, exclude_group_id: int | None = None) -> None:
        self.scene = scene
        self.project = get_or_404(session, Project, scene.project_id)
        all_chars = list(session.exec(select(Character).where(Character.project_id == scene.project_id)))
        self.cast = [c for c in all_chars if c.id in scene.cast_ids] or all_chars
        self.all_chars = all_chars
        self.location = session.get(Location, scene.location_id) if scene.location_id else None
        earlier = session.exec(
            select(Scene)
            .where(Scene.project_id == scene.project_id, Scene.order < scene.order)
            .order_by(Scene.order)
        )
        self.previous_summaries = [s.summary for s in earlier if s.summary]
        self.approved_blocks = [
            group_lines(session, g.id)
            for g in scene_groups(session, scene.id)
            if g.status in APPROVED_STATES and g.id != exclude_group_id
        ]

    def text(self) -> str:
        return prompts.story_context(
            self.project, self.scene, self.cast, self.location, self.previous_summaries, self.approved_blocks
        )

    def resolve_speaker(self, name: str) -> tuple[int | None, str]:
        n = name.strip().lower()
        if not n or n in ("narrator", "narration"):
            return None, "Narrator"
        for c in self.all_chars:
            if c.name.lower() == n:
                return c.id, c.name
        for c in self.all_chars:
            first = c.name.lower().split()[0]
            if first == n.split()[0] or n in c.name.lower():
                return c.id, c.name
        return None, name.strip()


def _write_lines(session: Session, group: DialogueGroup, lines: list[dict], ctx: SceneContext | None) -> None:
    for old in group_lines(session, group.id):
        session.delete(old)
    for i, l in enumerate(lines):
        if ctx and "speaker" in l:
            sid, sname = ctx.resolve_speaker(l["speaker"])
        else:
            sid, sname = l.get("speaker_id"), l.get("speaker_name") or "Narrator"
        session.add(
            DialogueLine(
                group_id=group.id,
                order=i,
                speaker_id=sid,
                speaker_name=sname,
                text=l.get("text", ""),
                emotion=l.get("emotion", ""),
                action=l.get("action", ""),
            )
        )


async def generate_next_group(session: Session, scene_id: int, guidance: str, size: int) -> DialogueGroup:
    scene = get_or_404(session, Scene, scene_id)
    if scene.status == "complete":
        raise HTTPException(400, "Scene is complete; reopen it to continue writing")
    groups = scene_groups(session, scene_id)
    if any(g.status == DRAFT for g in groups):
        raise HTTPException(400, "Approve or delete the current draft block before generating the next one")
    ctx = SceneContext(session, scene)
    result = await LLMProvider().chat_json(
        prompts.WRITER_SYSTEM,
        prompts.dialogue_group_prompt(ctx.text(), ctx.cast, size, guidance),
        validate=prompts.validate_group,
    )
    group = DialogueGroup(scene_id=scene_id, order=len(groups), guidance=guidance)
    session.add(group)
    session.commit()
    session.refresh(group)
    _write_lines(session, group, result["lines"], ctx)
    scene.llm_suggests_complete = result["scene_complete"]
    session.add(scene)
    session.commit()
    session.refresh(group)
    return group


async def regenerate_group(session: Session, group_id: int, guidance: str, size: int | None) -> DialogueGroup:
    group = get_or_404(session, DialogueGroup, group_id)
    if group.status != DRAFT:
        raise HTTPException(400, "Only draft blocks can be regenerated (unapprove it first)")
    scene = get_or_404(session, Scene, group.scene_id)
    ctx = SceneContext(session, scene, exclude_group_id=group.id)
    size = size or max(3, len(group_lines(session, group.id)))
    result = await LLMProvider().chat_json(
        prompts.WRITER_SYSTEM,
        prompts.dialogue_group_prompt(ctx.text(), ctx.cast, size, guidance or group.guidance),
        validate=prompts.validate_group,
    )
    if guidance:
        group.guidance = guidance
    _write_lines(session, group, result["lines"], ctx)
    scene.llm_suggests_complete = result["scene_complete"]
    session.add_all([group, scene])
    session.commit()
    session.refresh(group)
    return group


async def regenerate_line(session: Session, line_id: int, guidance: str) -> DialogueLine:
    line = get_or_404(session, DialogueLine, line_id)
    group = get_or_404(session, DialogueGroup, line.group_id)
    scene = get_or_404(session, Scene, group.scene_id)
    ctx = SceneContext(session, scene, exclude_group_id=group.id)
    block = group_lines(session, group.id)
    index = next(i for i, l in enumerate(block) if l.id == line.id)
    result = await LLMProvider().chat_json(
        prompts.WRITER_SYSTEM,
        prompts.regenerate_line_prompt(ctx.text(), block, index, ctx.cast, guidance),
        validate=prompts.validate_line,
    )
    line.speaker_id, line.speaker_name = ctx.resolve_speaker(result["speaker"])
    line.text, line.emotion, line.action = result["text"], result["emotion"], result["action"]
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


def replace_lines(session: Session, group_id: int, lines: list[dict]) -> DialogueGroup:
    group = get_or_404(session, DialogueGroup, group_id)
    _write_lines(session, group, lines, None)
    session.commit()
    session.refresh(group)
    return group


def rebuild_prompt(session: Session, group: DialogueGroup) -> None:
    scene = get_or_404(session, Scene, group.scene_id)
    project = get_or_404(session, Project, scene.project_id)
    settings = get_settings()
    chars = {c.id: c for c in session.exec(select(Character).where(Character.project_id == scene.project_id))}
    location = session.get(Location, scene.location_id) if scene.location_id else None
    built = build_scene_prompt(
        group.shot,
        chars,
        location,
        project.style_preset or settings.style_preset,
        settings.negative_prompt,
    )
    group.prompt = built.prompt
    group.negative_prompt = built.negative
    group.warnings = built.warnings


async def make_shot(session: Session, group: DialogueGroup) -> None:
    scene = get_or_404(session, Scene, group.scene_id)
    project = get_or_404(session, Project, scene.project_id)
    ctx = SceneContext(session, scene)
    style = STYLE_PRESETS.get(project.style_preset or get_settings().style_preset, STYLE_PRESETS["anime_vn"])
    shot = await LLMProvider().chat_json(
        prompts.DIRECTOR_SYSTEM,
        prompts.shot_prompt(group_lines(session, group.id), ctx.cast, ctx.location, style["label"]),
        temperature=0.5,
        validate=prompts.validate_shot,
    )
    valid_ids = {c.id for c in ctx.all_chars}
    shot["characters"] = [c for c in shot["characters"] if c["id"] in valid_ids]
    if not shot["characters"]:
        speakers = {l.speaker_id for l in group_lines(session, group.id) if l.speaker_id}
        shot["characters"] = [
            {"id": sid, "expression": "", "pose": "", "position": "", "outfit": ""} for sid in speakers
        ]
    group.shot = shot
    rebuild_prompt(session, group)


async def approve_group(session: Session, group_id: int) -> DialogueGroup:
    group = get_or_404(session, DialogueGroup, group_id)
    if not group_lines(session, group.id):
        raise HTTPException(400, "Cannot approve an empty block")
    await make_shot(session, group)
    group.status = "approved"
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def unapprove_group(session: Session, group_id: int) -> DialogueGroup:
    group = get_or_404(session, DialogueGroup, group_id)
    group.status = DRAFT
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


async def complete_scene(session: Session, scene_id: int) -> Scene:
    scene = get_or_404(session, Scene, scene_id)
    groups = scene_groups(session, scene_id)
    if any(g.status == DRAFT for g in groups):
        raise HTTPException(400, "Approve or delete the draft block before completing the scene")
    blocks = [group_lines(session, g.id) for g in groups]
    if blocks:
        scene.summary = await LLMProvider().chat_json(
            prompts.WRITER_SYSTEM,
            prompts.summary_prompt(scene, blocks),
            temperature=0.3,
            validate=prompts.validate_summary,
        )
    scene.status = "complete"
    session.add(scene)
    session.commit()
    session.refresh(scene)
    return scene
