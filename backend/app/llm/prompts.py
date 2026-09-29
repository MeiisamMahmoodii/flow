"""Prompt builders and validators for the writing pipeline."""

from typing import Any

from ..models import Character, DialogueLine, Location, Project, Scene

WRITER_SYSTEM = """You are the lead writer of a visual novel. You write vivid, in-character dialogue \
for an adult creative-fiction project. Stay fully in the fiction, follow the director's notes, keep every \
character consistent with their sheet (personality, speech style, relationships), and move the scene \
toward its goal without rushing it. You always answer with a single JSON object and nothing else."""

DIRECTOR_SYSTEM = """You are the art director of a visual novel. You turn a block of dialogue into one \
illustrated CG/scene image description. You always answer with a single JSON object and nothing else."""


def character_sheet(ch: Character) -> str:
    parts = [f"### {ch.name} (id={ch.id})"]
    for label, value in (
        ("Description", ch.description),
        ("Personality", ch.personality),
        ("Speech style", ch.speech_style),
        ("Appearance", ch.appearance),
        ("Relationships", ch.relationships),
    ):
        if value.strip():
            parts.append(f"- {label}: {value.strip()}")
    return "\n".join(parts)


def format_lines(lines: list[DialogueLine]) -> str:
    out = []
    for l in lines:
        meta = ", ".join(x for x in (l.emotion, l.action) if x)
        prefix = f"{l.speaker_name}" + (f" [{meta}]" if meta else "")
        out.append(f"{prefix}: {l.text}")
    return "\n".join(out)


def story_context(
    project: Project,
    scene: Scene,
    cast: list[Character],
    location: Location | None,
    previous_summaries: list[str],
    approved_blocks: list[list[DialogueLine]],
) -> str:
    sections = [f"## Story premise\n{project.premise.strip() or '(none given)'}"]
    if previous_summaries:
        sections.append(
            "## Story so far (previous scenes)\n" + "\n".join(f"- {s}" for s in previous_summaries if s)
        )
    sections.append("## Characters in this scene\n" + ("\n\n".join(character_sheet(c) for c in cast) or "(none)"))
    loc = f"{location.name}: {location.description}" if location else "(unspecified)"
    sections.append(
        f"## Current scene: {scene.title}\n- Location: {loc}\n- Scene goal: {scene.goal or '(open)'}\n"
        f"- Outline: {scene.outline or '(open)'}"
    )
    if approved_blocks:
        body = "\n\n".join(f"[Block {i + 1}]\n{format_lines(b)}" for i, b in enumerate(approved_blocks))
        sections.append(f"## Dialogue written so far in this scene (approved)\n{body}")
    else:
        sections.append("## Dialogue written so far in this scene\n(nothing yet - this is the opening block)")
    return "\n\n".join(sections)


def dialogue_group_prompt(context: str, cast: list[Character], size: int, guidance: str) -> str:
    names = ", ".join([c.name for c in cast] + ["Narrator"])
    return f"""{context}

## Task
Write the NEXT block of the scene: about {size} lines that continue naturally from the dialogue so far.
Allowed speakers: {names}. Use "Narrator" for narration, inner thoughts framing, or scene description.
{f"Director's notes for this block: {guidance}" if guidance.strip() else ""}

Return JSON exactly in this shape:
{{
  "lines": [
    {{"speaker": "<name from allowed speakers>", "text": "<spoken line or narration>", "emotion": "<one or two words>", "action": "<short stage direction or empty>"}}
  ],
  "scene_complete": <true if the scene goal is reached after this block, else false>
}}"""


def regenerate_line_prompt(context: str, block: list[DialogueLine], index: int, cast: list[Character], guidance: str) -> str:
    names = ", ".join([c.name for c in cast] + ["Narrator"])
    numbered = "\n".join(
        f"{'>>' if i == index else '  '} {i + 1}. {l.speaker_name}: {l.text}" for i, l in enumerate(block)
    )
    return f"""{context}

## Block being edited (line {index + 1} marked with >>)
{numbered}

## Task
Rewrite ONLY line {index + 1} so it fits better between its neighbours. Allowed speakers: {names}.
{f"Director's notes: {guidance}" if guidance.strip() else ""}

Return JSON: {{"speaker": "...", "text": "...", "emotion": "...", "action": "..."}}"""


def shot_prompt(
    lines: list[DialogueLine], cast: list[Character], location: Location | None, style_hint: str
) -> str:
    cast_desc = "\n".join(
        f"- id={c.id} {c.name}: {c.appearance or c.description} (tags: {c.appearance_tags})" for c in cast
    )
    loc = f"{location.name}: {location.description} (tags: {location.tags})" if location else "(unspecified)"
    return f"""## Cast available
{cast_desc or '(none)'}

## Location
{loc}

## Dialogue block to illustrate
{format_lines(lines)}

## Task
Design ONE illustration (visual novel CG) that best represents this dialogue block. Only include \
characters who are visibly present. Describe the dominant emotion per character at this moment.
Style target: {style_hint}.
Write every descriptive field as short comma-separated image-generation tags (danbooru style), not sentences.

Return JSON:
{{
  "characters": [{{"id": <cast id>, "expression": "tags", "pose": "tags", "position": "left|center|right", "outfit": "tags or empty"}}],
  "camera": "tags e.g. cowboy shot, from side, close-up",
  "background": "tags describing the environment",
  "lighting": "tags",
  "mood": "tags",
  "extra_tags": "any other tags (props, effects)"
}}"""


def summary_prompt(scene: Scene, blocks: list[list[DialogueLine]]) -> str:
    body = "\n\n".join(format_lines(b) for b in blocks)
    return f"""Scene "{scene.title}" dialogue:

{body}

Summarize what happened in this scene in 2-4 sentences for continuity notes (who, what changed, \
emotional state at the end). Return JSON: {{"summary": "..."}}"""


def expand_character_prompt(project: Project, name: str, brief: str) -> str:
    return f"""Story premise: {project.premise or '(none)'}

Create a visual novel character sheet for "{name}". Brief from the author: {brief or '(none)'}

Return JSON:
{{
  "description": "one-paragraph role in the story",
  "personality": "traits, quirks, fears, desires",
  "speech_style": "how they talk: vocabulary, verbal tics, formality",
  "appearance": "natural-language look description",
  "appearance_tags": "comma-separated danbooru tags for their fixed look, e.g. 1girl, long silver hair, red eyes",
  "relationships": "relationships to other characters if implied"
}}"""


# ---------- validators ----------


def validate_group(data: Any) -> dict:
    if isinstance(data, list):
        data = {"lines": data}
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not lines:
        raise ValueError('expected {"lines": [...]} with at least one line')
    clean = []
    for l in lines:
        if not isinstance(l, dict) or not str(l.get("text", "")).strip():
            continue
        clean.append(
            {
                "speaker": str(l.get("speaker") or "Narrator").strip(),
                "text": str(l["text"]).strip(),
                "emotion": str(l.get("emotion") or "").strip(),
                "action": str(l.get("action") or "").strip(),
            }
        )
    if not clean:
        raise ValueError("no usable lines with text")
    return {"lines": clean, "scene_complete": bool(data.get("scene_complete", False))}


def validate_line(data: Any) -> dict:
    if isinstance(data, dict) and "lines" in data and data["lines"]:
        data = data["lines"][0]
    if not isinstance(data, dict) or not str(data.get("text", "")).strip():
        raise ValueError('expected {"speaker","text","emotion","action"}')
    return validate_group({"lines": [data]})["lines"][0]


def validate_shot(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    chars = []
    for c in data.get("characters") or []:
        if not isinstance(c, dict):
            continue
        try:
            cid = int(c.get("id"))
        except (TypeError, ValueError):
            continue
        chars.append(
            {
                "id": cid,
                "expression": str(c.get("expression") or ""),
                "pose": str(c.get("pose") or ""),
                "position": str(c.get("position") or ""),
                "outfit": str(c.get("outfit") or ""),
            }
        )
    out = {"characters": chars}
    for key in ("camera", "background", "lighting", "mood", "extra_tags"):
        val = data.get(key) or ""
        out[key] = ", ".join(map(str, val)) if isinstance(val, list) else str(val)
    return out


def validate_summary(data: Any) -> str:
    if isinstance(data, dict) and str(data.get("summary", "")).strip():
        return str(data["summary"]).strip()
    raise ValueError('expected {"summary": "..."}')


def validate_character(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    keys = ("description", "personality", "speech_style", "appearance", "appearance_tags", "relationships")
    return {k: (", ".join(data[k]) if isinstance(data.get(k), list) else str(data.get(k) or "")) for k in keys}
