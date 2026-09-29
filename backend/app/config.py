import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("VNFLOW_DATA", ROOT_DIR / "data")).resolve()
SETTINGS_FILE = DATA_DIR / "settings.json"

LLM_PRESETS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}


class Settings(BaseModel):
    llm_provider: Literal["ollama", "lmstudio", "custom"] = "ollama"
    llm_base_url: str = LLM_PRESETS["ollama"]
    llm_api_key: str = "local"
    llm_model: str = ""
    llm_vision_model: str = ""
    llm_temperature: float = 0.9
    llm_max_tokens: int = 2048
    llm_json_mode: bool = True

    image_backend: Literal["diffusers", "comfyui"] = "diffusers"
    checkpoint_dir: str = str(DATA_DIR / "models")
    default_checkpoint: str = ""
    device: Literal["auto", "cuda", "mps", "cpu"] = "auto"
    dtype: Literal["auto", "float16", "bfloat16", "float32"] = "auto"

    comfy_url: str = "http://127.0.0.1:8188"
    comfy_lora_dir: str = ""
    comfy_checkpoint: str = ""
    comfy_sampler: str = "euler_ancestral"
    comfy_scheduler: str = "normal"

    style_preset: str = "anime_vn"
    width: int = 1216
    height: int = 832
    steps: int = 28
    cfg: float = 6.0
    variants: int = 2
    negative_prompt: str = ""

    ip_adapter_repo: str = "h94/IP-Adapter"
    ip_adapter_subfolder: str = "sdxl_models"
    # The face variant transfers identity without taking over pose and composition.
    ip_adapter_weight: str = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
    ip_adapter_image_encoder: str = "models/image_encoder"
    ip_adapter_scale: float = 0.45

    captioner: Literal["wd14", "vision_llm"] = "wd14"
    wd14_repo: str = "SmilingWolf/wd-vit-tagger-v3"
    wd14_threshold: float = 0.35


_lock = threading.Lock()
_settings: Settings | None = None


def ensure_dirs() -> None:
    for sub in ("projects", "characters", "loras", "models", "training", "exports", "tmp"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    global _settings
    with _lock:
        if _settings is None:
            if SETTINGS_FILE.exists():
                _settings = Settings(**json.loads(SETTINGS_FILE.read_text()))
            else:
                _settings = Settings()
        return _settings


def save_settings(new: Settings) -> Settings:
    global _settings
    with _lock:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(new.model_dump_json(indent=2))
        _settings = new
        return new


def rel_data_path(path: Path | str) -> str:
    """Path relative to DATA_DIR, used for URLs under /files."""
    return Path(path).resolve().relative_to(DATA_DIR).as_posix()


def abs_data_path(rel: str) -> Path:
    return (DATA_DIR / rel).resolve()
