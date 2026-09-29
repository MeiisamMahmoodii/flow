"""Turns a structured shot description + character/location data into a diffusion prompt."""

from dataclasses import dataclass, field
from pathlib import Path

from ..config import abs_data_path
from ..models import Character, Location
from .base import LoraSpec

STYLE_PRESETS: dict[str, dict[str, str]] = {
    "anime_vn": {
        "label": "Anime VN (SDXL / Illustrious / NoobAI)",
        "positive": "masterpiece, best quality, amazing quality, visual novel cg, anime coloring, detailed background",
        "negative": "lowres, worst quality, bad quality, bad anatomy, bad hands, extra fingers, jpeg artifacts, "
        "signature, watermark, text, blurry, cropped",
    },
    "pony": {
        "label": "Pony Diffusion",
        "positive": "score_9, score_8_up, score_7_up, source_anime, visual novel cg, detailed background",
        "negative": "score_4, score_5, score_6, lowres, bad anatomy, bad hands, watermark, text, blurry",
    },
    "semi_real": {
        "label": "Semi-realistic",
        "positive": "masterpiece, best quality, semi-realistic, cinematic lighting, detailed illustration, "
        "highly detailed background",
        "negative": "lowres, worst quality, bad anatomy, deformed, disfigured, extra limbs, watermark, text, blurry",
    },
    "painterly": {
        "label": "Painterly",
        "positive": "masterpiece, best quality, digital painting, painterly, soft brush strokes, atmospheric",
        "negative": "lowres, worst quality, bad anatomy, photo, 3d, watermark, text, blurry",
    },
    "none": {"label": "No preset", "positive": "", "negative": ""},
}

MAX_IP_REFS_PER_CHAR = 2
BREAK = "BREAK"


@dataclass
class BuiltPrompt:
    prompt: str
    negative: str
    loras: list[LoraSpec] = field(default_factory=list)
    ip_refs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _join(*parts: str) -> str:
    seen: set[str] = set()
    tags: list[str] = []
    for part in parts:
        for tag in (part or "").replace("\n", ",").split(","):
            tag = tag.strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag)
    return ", ".join(tags)


def lora_for(ch: Character) -> LoraSpec | None:
    if not ch.lora_path:
        return None
    path = Path(ch.lora_path)
    if not path.is_absolute():
        path = abs_data_path(ch.lora_path)
    if not path.exists():
        return None
    safe = "".join(c if c.isalnum() else "_" for c in f"char{ch.id}_{path.stem}")
    return LoraSpec(path=path, weight=ch.lora_weight, name=safe)


def ref_paths(ch: Character, limit: int = MAX_IP_REFS_PER_CHAR) -> list[Path]:
    out = []
    for r in ch.ref_images[:limit]:
        p = abs_data_path(r["file"])
        if p.exists():
            out.append(p)
    return out


def count_tag(n: int) -> str:
    return {0: "no humans", 1: "solo"}.get(n, "multiple people" if n > 3 else f"{n}people")


def build_scene_prompt(
    shot: dict,
    cast: dict[int, Character],
    location: Location | None,
    style: str,
    global_negative: str = "",
    use_ip_adapter: bool = True,
) -> BuiltPrompt:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["anime_vn"])
    present = [c for c in shot.get("characters", []) if c.get("id") in cast]
    char_parts: list[str] = []
    loras: list[LoraSpec] = []
    ip_refs: list[Path] = []
    warnings: list[str] = []

    for entry in present:
        ch = cast[entry["id"]]
        lora = lora_for(ch)
        if lora:
            loras.append(lora)
        elif use_ip_adapter:
            ip_refs.extend(ref_paths(ch))
        char_parts.append(
            _join(
                ch.trigger_word if lora else "",
                ch.appearance_tags,
                entry.get("outfit", ""),
                entry.get("expression", ""),
                entry.get("pose", ""),
                f"on {entry['position']}" if entry.get("position") and len(present) > 1 else "",
            )
        )

    if len(loras) > 2:
        warnings.append(
            f"{len(loras)} character LoRAs in one image - features may bleed between characters. "
            "Consider fewer characters per shot or lowering LoRA weights."
        )
    if loras and ip_refs:
        warnings.append("Mixing LoRA and reference-image (IP-Adapter) characters; consistency may vary.")
    missing = [cast[e["id"]].name for e in present if not lora_for(cast[e["id"]]) and not ref_paths(cast[e["id"]])]
    if missing:
        warnings.append(f"No LoRA or reference images for: {', '.join(missing)} (prompt tags only).")

    loc_tags = location.tags if location else ""
    head = _join(preset["positive"], count_tag(len(present)), shot.get("camera", ""))
    tail = _join(
        shot.get("background", ""),
        loc_tags,
        shot.get("lighting", ""),
        shot.get("mood", ""),
        shot.get("extra_tags", ""),
    )
    if len(char_parts) > 1:
        # Each character gets its own CLIP chunk to reduce attribute bleed between characters.
        prompt = f" {BREAK} ".join(p for p in (head, *char_parts, tail) if p)
    else:
        prompt = _join(head, *char_parts, tail)
    negative = _join(preset["negative"], global_negative)
    return BuiltPrompt(prompt=prompt, negative=negative, loras=loras, ip_refs=ip_refs, warnings=warnings)


def build_character_test_prompt(ch: Character, extra: str, style: str, global_negative: str = "") -> BuiltPrompt:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["anime_vn"])
    lora = lora_for(ch)
    prompt = _join(
        preset["positive"],
        "solo",
        ch.trigger_word if lora else "",
        ch.appearance_tags,
        extra or "upper body, looking at viewer, simple background",
    )
    return BuiltPrompt(
        prompt=prompt,
        negative=_join(preset["negative"], global_negative),
        loras=[lora] if lora else [],
        ip_refs=[] if lora else ref_paths(ch, 4),
    )


def build_background_prompt(loc: Location, extra: str, style: str, global_negative: str = "") -> BuiltPrompt:
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["anime_vn"])
    prompt = _join(preset["positive"], "no humans, scenery", loc.tags, loc.description if not loc.tags else "", extra)
    return BuiltPrompt(prompt=prompt, negative=_join(preset["negative"], global_negative, "1girl, 1boy, people"))
