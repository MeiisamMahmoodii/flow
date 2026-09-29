import asyncio

from fastapi import APIRouter, Body, HTTPException

from ..config import LLM_PRESETS, Settings, get_settings, save_settings
from ..imaging.device import device_info
from ..imaging.prompt_builder import STYLE_PRESETS
from ..imaging.registry import get_backend, unload_all
from ..llm.provider import LLMError, LLMProvider

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/settings")
def read_settings() -> Settings:
    return get_settings()


@router.put("/settings")
def write_settings(data: dict = Body(...)) -> Settings:
    current = get_settings()
    merged = current.model_dump() | data
    if data.get("llm_provider") in LLM_PRESETS and "llm_base_url" not in data:
        merged["llm_base_url"] = LLM_PRESETS[data["llm_provider"]]
    new = Settings(**merged)
    image_changed = any(
        getattr(current, k) != getattr(new, k) for k in ("default_checkpoint", "device", "dtype", "checkpoint_dir")
    )
    saved = save_settings(new)
    if image_changed:
        unload_all()
    return saved


@router.get("/system/info")
async def system_info() -> dict:
    return {
        "device": await asyncio.to_thread(device_info),
        "backend": get_backend().status(),
        "style_presets": {k: v["label"] for k, v in STYLE_PRESETS.items()},
        "llm_presets": LLM_PRESETS,
    }


@router.get("/llm/models")
async def llm_models() -> list[str]:
    try:
        return await LLMProvider().list_models()
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/llm/test")
async def llm_test() -> dict:
    try:
        reply = await LLMProvider().chat(
            [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=512
        )
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"reply": reply.strip()[:200]}


@router.get("/image/models")
async def image_models() -> list[str]:
    try:
        return await asyncio.to_thread(get_backend().list_models)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/image/unload")
def image_unload() -> dict:
    unload_all()
    return {"ok": True}
