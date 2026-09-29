"""OpenAI-compatible chat client for local servers (Ollama, LM Studio, llama.cpp, vLLM...)."""

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings, get_settings

log = logging.getLogger("vnflow.llm")


class LLMError(RuntimeError):
    pass


THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _balanced_json(text: str) -> str | None:
    start = None
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if start is None:
            if ch in "{[":
                start = i
                depth = 1
            continue
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from model output (handles think tags, fences, trailing commas)."""
    cleaned = THINK_RE.sub("", text).strip()
    # Unclosed <think> (truncated reasoning) - drop everything before the last </think> if present
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1]
    candidates = [cleaned]
    candidates += FENCE_RE.findall(cleaned)
    bal = _balanced_json(cleaned)
    if bal:
        candidates.append(bal)
    for cand in candidates:
        for variant in (cand, TRAILING_COMMA_RE.sub(r"\1", cand)):
            try:
                return json.loads(variant)
            except (json.JSONDecodeError, TypeError):
                continue
    raise ValueError("No valid JSON found in model output")


class LLMProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.llm_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.llm_api_key or 'local'}"}

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
                r.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMError(f"Cannot reach LLM server at {self.base_url}: {exc}") from exc
            data = r.json().get("data", [])
            return sorted(m.get("id", "") for m in data if m.get("id"))

    async def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        model = model or self.settings.llm_model
        if not model:
            models = await self.list_models()
            if not models:
                raise LLMError("No LLM model configured and the server reports no models")
            model = models[0]
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
            "stream": False,
        }
        use_json = json_mode and self.settings.llm_json_mode
        if use_json:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
            try:
                r = await client.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers())
                if r.status_code == 400 and use_json:
                    # LM Studio and some servers reject json_object; retry without it.
                    body.pop("response_format", None)
                    r = await client.post(
                        f"{self.base_url}/chat/completions", json=body, headers=self._headers()
                    )
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"LLM request failed ({exc.response.status_code}): {exc.response.text[:500]}")
            except httpx.HTTPError as exc:
                raise LLMError(f"Cannot reach LLM server at {self.base_url}: {exc}") from exc
        data = r.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected LLM response: {str(data)[:300]}") from exc

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        retries: int = 2,
        validate: Any = None,
    ) -> Any:
        """Ask for JSON; on parse/validation failure feed the error back and retry."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err = ""
        for attempt in range(retries + 1):
            raw = await self.chat(messages, json_mode=True, temperature=temperature)
            try:
                parsed = extract_json(raw)
                if validate:
                    parsed = validate(parsed)
                return parsed
            except Exception as exc:
                last_err = str(exc)
                log.warning("LLM JSON attempt %s failed: %s", attempt + 1, exc)
                messages = messages[:2] + [
                    {"role": "assistant", "content": raw[:4000]},
                    {
                        "role": "user",
                        "content": f"That output was invalid ({last_err}). "
                        "Reply again with ONLY the corrected JSON object, no commentary.",
                    },
                ]
        raise LLMError(f"LLM did not return valid JSON after {retries + 1} attempts: {last_err}")

    async def describe_image(self, image_path: Path, prompt: str) -> str:
        model = self.settings.llm_vision_model
        if not model:
            raise LLMError("Set a vision model (e.g. qwen2.5vl, llava) in Settings to caption with an LLM")
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ]
        text = await self.chat(messages, model=model, temperature=0.2, max_tokens=300)
        return THINK_RE.sub("", text).strip()
