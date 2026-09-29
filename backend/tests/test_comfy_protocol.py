"""Runs ComfyUIBackend against a minimal fake ComfyUI server (HTTP + WebSocket)."""

import asyncio
import io
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import Response
from PIL import Image

from app.config import Settings, save_settings
from app.imaging.base import ImageRequest, LoraSpec
from app.imaging.comfy_backend import ComfyUIBackend


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_fake_comfy() -> tuple[FastAPI, dict]:
    app = FastAPI()
    state: dict = {"prompts": [], "sockets": {}}

    @app.get("/object_info/{node}")
    def object_info(node: str):
        field = {"CheckpointLoaderSimple": "ckpt_name", "LoraLoader": "lora_name"}[node]
        return {node: {"input": {"required": {field: [["model.safetensors", "vnflow/mira.safetensors"]]}}}}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, clientId: str):
        await websocket.accept()
        state["sockets"][clientId] = websocket
        try:
            while True:
                await asyncio.sleep(0.05)
                pending = state.pop(f"run:{clientId}", None)
                if pending:
                    for step in (1, 2):
                        await websocket.send_json({"type": "progress", "data": {"value": step, "max": 2, "prompt_id": pending}})
                    await websocket.send_bytes(b"preview")
                    await websocket.send_json({"type": "executing", "data": {"node": None, "prompt_id": pending}})
        except Exception:
            pass

    @app.post("/prompt")
    async def prompt(body: dict):
        pid = f"p{len(state['prompts'])}"
        state["prompts"].append(body["prompt"])
        state[f"run:{body['client_id']}"] = pid
        return {"prompt_id": pid}

    @app.get("/history/{pid}")
    def history(pid: str):
        return {pid: {"outputs": {"save": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}

    @app.get("/view")
    def view():
        buf = io.BytesIO()
        Image.new("RGB", (64, 32), "red").save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png")

    return app, state


@pytest.fixture()
def fake_comfy(tmp_path):
    app, state = make_fake_comfy()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    lora_dir = tmp_path / "comfy_loras"
    save_settings(Settings(comfy_url=f"http://127.0.0.1:{port}", comfy_lora_dir=str(lora_dir)))
    yield state, lora_dir
    server.should_exit = True
    thread.join(timeout=5)


def test_generate_through_fake_comfy(fake_comfy, tmp_path):
    state, lora_dir = fake_comfy
    lora = tmp_path / "mira.safetensors"
    lora.write_bytes(b"x" * 10)
    progress: list[str] = []
    backend = ComfyUIBackend()

    assert backend.list_models() == ["model.safetensors", "vnflow/mira.safetensors"]
    req = ImageRequest(prompt="a BREAK b", seed=5, num_images=2, loras=[LoraSpec(lora, 0.7, "mira")])
    out = backend.generate(req, lambda f, m: progress.append(m), threading.Event())

    assert [r.seed for r in out] == [5, 6]
    assert out[0].image.size == (64, 32)
    assert (lora_dir / "vnflow" / "mira.safetensors").exists()
    wf = state["prompts"][0]
    assert wf["pos"]["inputs"]["text"] == "a, b"
    assert wf["lora_0"]["inputs"]["lora_name"] == "vnflow/mira.safetensors"
    assert wf["sampler"]["inputs"]["model"] == ["lora_0", 0]
    assert any("step 2/2" in m for m in progress)
