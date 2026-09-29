import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import DATA_DIR, ROOT_DIR, ensure_dirs
from .db import init_db
from .jobs import manager

# Job handlers register themselves on import.
from .imaging import service as _image_service  # noqa: F401
from .training import jobs as _training_jobs  # noqa: F401
from .routers import crud, export, flow, jobs, system, training

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    init_db()
    manager.start()
    yield


app = FastAPI(title="VN Flow", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (crud.router, flow.router, jobs.router, system.router, training.router, export.router):
    app.include_router(r)

ensure_dirs()
app.mount("/files", StaticFiles(directory=DATA_DIR), name="files")

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "files/", "ws")):
            raise HTTPException(404)
        target = FRONTEND_DIST / path
        if path and target.is_file() and Path(target).resolve().is_relative_to(FRONTEND_DIST):
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
