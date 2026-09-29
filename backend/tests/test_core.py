from app.imaging.comfy_backend import insert_loras, load_workflow, render
from app.imaging.prompt_builder import BREAK, build_scene_prompt
from app.llm.prompts import validate_group, validate_shot
from app.llm.provider import extract_json
from app.models import Character, Location


def test_extract_json_handles_think_tags_fences_and_trailing_commas():
    raw = '<think>plan the scene...</think>\nSure!\n```json\n{"lines": [{"speaker": "Mira", "text": "Hi",},],}\n```'
    assert extract_json(raw) == {"lines": [{"speaker": "Mira", "text": "Hi"}]}


def test_extract_json_finds_embedded_object():
    assert extract_json('Here you go: {"summary": "a {nested} brace"} hope it helps') == {"summary": "a {nested} brace"}


def test_validate_group_accepts_bare_list_and_drops_empty_lines():
    out = validate_group([{"speaker": "Mira", "text": "Hello"}, {"speaker": "Rowan", "text": "  "}])
    assert out["lines"] == [{"speaker": "Mira", "text": "Hello", "emotion": "", "action": ""}]
    assert out["scene_complete"] is False


def test_validate_shot_coerces_lists_and_ids():
    shot = validate_shot({"characters": [{"id": "2", "expression": "smile"}, {"id": "x"}], "camera": ["close-up", "from side"]})
    assert shot["characters"][0]["id"] == 2 and len(shot["characters"]) == 1
    assert shot["camera"] == "close-up, from side"


def _chars():
    return {
        1: Character(id=1, project_id=1, name="Mira", appearance_tags="1girl, glasses"),
        2: Character(id=2, project_id=1, name="Rowan", appearance_tags="1girl, red hair"),
    }


def test_scene_prompt_separates_characters_with_break():
    shot = {"characters": [{"id": 1, "expression": "shy"}, {"id": 2, "expression": "grin"}], "camera": "cowboy shot"}
    built = build_scene_prompt(shot, _chars(), Location(project_id=1, name="Lib", tags="library"), "anime_vn")
    segments = built.prompt.split(f" {BREAK} ")
    assert len(segments) == 4
    assert "glasses" in segments[1] and "red hair" in segments[2]
    assert "library" in segments[3]
    assert any("No LoRA" in w for w in built.warnings)


def test_single_character_prompt_has_no_break():
    built = build_scene_prompt({"characters": [{"id": 1}]}, _chars(), None, "anime_vn")
    assert BREAK not in built.prompt and "solo" in built.prompt


def test_comfy_workflow_render_and_lora_chain():
    values = dict(checkpoint="x.safetensors", prompt="p", negative="n", width=832, height=576, steps=20, cfg=6.0,
                  sampler="euler", scheduler="normal", strength=0.5, seed=7)
    wf = insert_loras(render(load_workflow("txt2img"), values), [("vnflow/a.safetensors", 0.8), ("b.safetensors", 0.6)])
    assert wf["latent"]["inputs"]["width"] == 832 and wf["sampler"]["inputs"]["seed"] == 7
    assert wf["lora_0"]["inputs"]["model"] == ["ckpt", 0]
    assert wf["lora_1"]["inputs"]["model"] == ["lora_0", 0]
    assert wf["sampler"]["inputs"]["model"] == ["lora_1", 0]
    assert wf["pos"]["inputs"]["clip"] == ["lora_1", 1]
    assert wf["decode"]["inputs"]["vae"] == ["ckpt", 2]
