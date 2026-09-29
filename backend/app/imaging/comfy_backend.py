"""ComfyUI adapter: fills bundled API-format workflows so the user never touches a node graph."""

import copy
import io
import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx
from PIL import Image
from websockets.sync.client import connect

from ..config import get_settings
from .base import GeneratedImage, GenerationCancelled, ImageRequest, LoraSpec, ProgressFn

WORKFLOW_DIR = Path(__file__).parent / "workflows"
LORA_SUBDIR = "vnflow"


def load_workflow(name: str) -> dict:
    return json.loads((WORKFLOW_DIR / f"{name}.json").read_text())


def render(node: Any, values: dict[str, Any]) -> Any:
    """Replace "{{key}}" string placeholders, preserving the value's type."""
    if isinstance(node, dict):
        return {k: render(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [render(v, values) for v in node]
    if isinstance(node, str) and node.startswith("{{") and node.endswith("}}"):
        return values[node[2:-2]]
    return node


def insert_loras(wf: dict, loras: list[tuple[str, float]]) -> dict:
    """Chain LoraLoader nodes after the checkpoint and rewire model/clip consumers."""
    if not loras:
        return wf
    wf = copy.deepcopy(wf)
    model_src, clip_src = ["ckpt", 0], ["ckpt", 1]
    lora_ids = []
    for i, (name, weight) in enumerate(loras):
        nid = f"lora_{i}"
        wf[nid] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": name,
                "strength_model": weight,
                "strength_clip": weight,
                "model": model_src,
                "clip": clip_src,
            },
        }
        model_src, clip_src = [nid, 0], [nid, 1]
        lora_ids.append(nid)
    for nid, node in wf.items():
        if nid in lora_ids:
            continue
        for key, val in node["inputs"].items():
            if val == ["ckpt", 0]:
                node["inputs"][key] = model_src
            elif val == ["ckpt", 1]:
                node["inputs"][key] = clip_src
    return wf


class ComfyUIBackend:
    name = "comfyui"
    supports_lora = True
    supports_ip_adapter = False

    @property
    def url(self) -> str:
        return get_settings().comfy_url.rstrip("/")

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.url, timeout=httpx.Timeout(120, connect=5))

    def status(self) -> dict:
        try:
            with self._client() as c:
                stats = c.get("/system_stats").raise_for_status().json()
            return {"backend": self.name, "available": True, "url": self.url, "system": stats.get("system", {})}
        except httpx.HTTPError as exc:
            return {"backend": self.name, "available": False, "url": self.url, "hint": f"ComfyUI not reachable: {exc}"}

    def _options(self, node: str, field: str) -> list[str]:
        with self._client() as c:
            info = c.get(f"/object_info/{node}").raise_for_status().json()
        return list(info[node]["input"]["required"][field][0])

    def list_models(self) -> list[str]:
        return self._options("CheckpointLoaderSimple", "ckpt_name")

    def list_loras(self) -> list[str]:
        return self._options("LoraLoader", "lora_name")

    def unload(self) -> None:
        try:
            with self._client() as c:
                c.post("/free", json={"unload_models": True, "free_memory": True})
        except httpx.HTTPError:
            pass

    def _sync_lora(self, spec: LoraSpec) -> str:
        lora_dir = get_settings().comfy_lora_dir
        if lora_dir:
            dest = Path(lora_dir).expanduser() / LORA_SUBDIR / spec.path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.stat().st_size != spec.path.stat().st_size:
                shutil.copy2(spec.path, dest)
            return f"{LORA_SUBDIR}/{spec.path.name}"
        available = self.list_loras()
        for name in available:
            if Path(name).name == spec.path.name:
                return name
        raise RuntimeError(
            f"LoRA {spec.path.name} is not in ComfyUI. Set 'ComfyUI LoRA folder' in Settings "
            "(e.g. ~/ComfyUI/models/loras) so VN Flow can sync trained LoRAs automatically."
        )

    def _upload(self, c: httpx.Client, path: Path) -> str:
        name = f"vnflow_{uuid.uuid4().hex[:8]}{path.suffix}"
        r = c.post(
            "/upload/image",
            files={"image": (name, path.read_bytes(), "image/png")},
            data={"overwrite": "true", "type": "input"},
        ).raise_for_status()
        data = r.json()
        return f"{data['subfolder']}/{data['name']}" if data.get("subfolder") else data["name"]

    def generate(self, req: ImageRequest, progress: ProgressFn, cancel: threading.Event) -> list[GeneratedImage]:
        s = get_settings()
        with self._client() as c:
            checkpoint = req.checkpoint or s.comfy_checkpoint
            if not checkpoint:
                models = self.list_models()
                if not models:
                    raise RuntimeError("ComfyUI reports no checkpoints")
                checkpoint = models[0]
            if req.ip_adapter_images:
                progress(0.0, "Reference images (IP-Adapter) are not used in ComfyUI mode")
            loras = [(self._sync_lora(l), l.weight) for l in req.loras]
            values: dict[str, Any] = {
                "checkpoint": checkpoint,
                "prompt": re.sub(r"\s*\bBREAK\b\s*", ", ", req.prompt),
                "negative": req.negative_prompt,
                "width": req.width,
                "height": req.height,
                "steps": req.steps,
                "cfg": req.cfg,
                "sampler": s.comfy_sampler,
                "scheduler": s.comfy_scheduler,
                "strength": req.strength,
            }
            template = "txt2img"
            if req.mode in ("img2img", "inpaint"):
                if not req.init_image:
                    raise ValueError(f"{req.mode} requires a source image")
                values["init_image"] = self._upload(c, req.init_image)
                template = req.mode
                if req.mode == "inpaint":
                    if not req.mask_image:
                        raise ValueError("inpaint requires a mask")
                    values["mask_image"] = self._upload(c, req.mask_image)

            results = []
            for i in range(req.num_images):
                values["seed"] = req.seed + i
                wf = insert_loras(render(load_workflow(template), values), loras)
                img = self._run_prompt(c, wf, i, req.num_images, progress, cancel)
                results.append(GeneratedImage(image=img, seed=req.seed + i))
            return results

    def _run_prompt(
        self, c: httpx.Client, wf: dict, idx: int, total: int, progress: ProgressFn, cancel: threading.Event
    ) -> Image.Image:
        client_id = uuid.uuid4().hex
        ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://") + f"/ws?clientId={client_id}"
        with connect(ws_url, max_size=None) as ws:
            r = c.post("/prompt", json={"prompt": wf, "client_id": client_id})
            if r.status_code != 200:
                raise RuntimeError(f"ComfyUI rejected workflow: {r.text[:800]}")
            prompt_id = r.json()["prompt_id"]
            progress(idx / total, f"Image {idx + 1}/{total} queued in ComfyUI")
            while True:
                if cancel.is_set():
                    c.post("/interrupt")
                    raise GenerationCancelled()
                try:
                    raw = ws.recv(timeout=1.0)
                except TimeoutError:
                    continue
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                data = msg.get("data", {})
                if data.get("prompt_id") not in (None, prompt_id):
                    continue
                if msg["type"] == "progress":
                    frac = (idx + data["value"] / max(1, data["max"])) / total
                    progress(min(frac, 0.99), f"Image {idx + 1}/{total} - step {data['value']}/{data['max']}")
                elif msg["type"] == "execution_error":
                    raise RuntimeError(f"ComfyUI error: {data.get('exception_message', data)}")
                elif msg["type"] == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                    break
                elif msg["type"] == "execution_success" and data.get("prompt_id") == prompt_id:
                    break
        history = c.get(f"/history/{prompt_id}").raise_for_status().json()[prompt_id]
        images = history["outputs"]["save"]["images"]
        info = images[0]
        view = c.get(
            "/view", params={"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")}
        ).raise_for_status()
        return Image.open(io.BytesIO(view.content)).convert("RGB")
