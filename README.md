# VN Flow - local visual novel studio

A Google Flow-style studio for **visual novels**, running entirely on your machine:

1. Create **characters** (personality, speech style, look) and **locations**.
2. The local LLM (Ollama / LM Studio) drafts a scene **one dialogue block at a time**.
3. You edit, rewrite or approve each block.
4. On approval, the LLM art-directs a shot and a local image model renders **an illustration for that block**.
5. Pick the best variant (or make a variation / inpaint), then continue with the next block until the scene is done.
6. Play the story in the browser or export it to **Ren'Py**. Unzip the export into your Ren'Py project's `game/` folder,
   and point your `label start:` at `jump vnflow_start`.

Character consistency comes from **per-character LoRAs trained in the app** from reference images, with IP-Adapter
(reference images) as a fallback until a LoRA exists.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed automatically) and Node 20+
- A writer model served by **Ollama** (`http://localhost:11434`) or **LM Studio** (`http://localhost:1234`).
  Any OpenAI-compatible server works. Uncensored / abliterated models are fine - the prompts don't fight them.
- An **SDXL-family checkpoint** (`.safetensors`): SDXL, Illustrious, NoobAI, Pony, RealVis, etc.
  Put it in `data/models/` or point Settings at any path / Hugging Face repo id.
- GPU: NVIDIA (CUDA) or Apple Silicon (MPS). CPU works but is very slow.

## Quick start

```bash
./scripts/dev.sh
# backend  -> http://127.0.0.1:8000  (API docs at /docs)
# frontend -> http://localhost:5173
```

Or manually:

```bash
cd backend && uv sync --extra image --extra tagger && uv run uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```

Then open **Settings**: pick the LLM provider and model, and the default checkpoint.

For a single-port setup, run `npm run build` in `frontend/`; the backend then serves the built UI at `http://127.0.0.1:8000`.

## Image backends

| Backend | What it does |
| --- | --- |
| **Built-in (diffusers)** | Loads checkpoints directly on CUDA/MPS. Supports character LoRAs, IP-Adapter references, img2img variations, inpainting, and prompts longer than 77 tokens (with `BREAK` to isolate each character's tags). |
| **ComfyUI** | Sends bundled preset workflows (`backend/app/imaging/workflows/*.json`) to a running ComfyUI. You never see the node graph. Set "ComfyUI LoRA folder" so trained LoRAs are synced to `models/loras/vnflow/`. IP-Adapter is not used in this mode. |

Only one GPU job (generation or training) runs at a time; the rest queue up in **Jobs**.

## Character LoRA training

On a character's **References & LoRA** tab:

1. Upload 5-20 clean images of the character, with varied poses and framing.
2. **Auto-caption** them with the WD14 tagger (offline, anime-oriented) or a vision LLM (set a vision model in Settings). Then edit the captions if needed.
3. Pick a preset and click **Train LoRA**. The trainer (`backend/app/training/train_sdxl_lora.py`) caches latents, trains the UNet attention layers, and saves kohya-format checkpoints with sample images along the way.
4. Pick the checkpoint whose samples look best (**Use this**). It then applies automatically whenever that character appears in a shot.

Training uses the default checkpoint from Settings, so train on the same base model you generate with.
Expect a few minutes to about half an hour on a modern NVIDIA GPU, and much longer on Apple Silicon.
Use the **Low memory** preset on 16 GB Macs. You can also import a LoRA you trained elsewhere (`.safetensors`).

## Data

Everything lives in `data/` (git-ignored): the SQLite DB, settings, generated images, reference images, LoRAs,
training runs and exports. To move it elsewhere, set `VNFLOW_DATA=/path/to/data`.

## Project layout

```
backend/app/
  main.py                 FastAPI app, static files, SPA
  models.py               SQLModel schema
  jobs.py                 async job queue + GPU lock + WebSocket hub
  llm/provider.py         OpenAI-compatible client (Ollama / LM Studio), JSON repair + retry
  llm/prompts.py          writer / art-director prompts and validators
  services/scene_flow.py  draft -> approve -> shot -> images -> next block state machine
  imaging/                backend interface, diffusers + ComfyUI backends, prompt builder
  training/               WD14 tagger, SDXL LoRA trainer, training jobs
  routers/                REST API
frontend/src/
  pages/                  Projects, Scenes, Characters, Locations, Scene editor, Play, Jobs, Settings
  components/             UI kit, VN preview, mask editor, lightbox
```

Run the backend tests with `cd backend && uv run pytest`.
