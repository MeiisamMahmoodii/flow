import asyncio
import json
import logging
import threading
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket
from sqlmodel import Session, select

from .db import engine
from .models import Job, utcnow

log = logging.getLogger("vnflow.jobs")

MAX_LOG_CHARS = 20000


class JobCancelled(Exception):
    pass


class Hub:
    """Fan-out of JSON events to all connected browser tabs."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        data = json.dumps(message, default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()


def job_to_dict(job: Job) -> dict:
    d = job.model_dump(mode="json")
    d["logs"] = d["logs"][-4000:]
    return d


class JobContext:
    """Handed to job handlers. Safe to call from worker threads."""

    def __init__(self, manager: "JobManager", job_id: int, payload: dict) -> None:
        self.manager = manager
        self.job_id = job_id
        self.payload = payload
        self.cancel_event = threading.Event()
        self.on_cancel: Callable[[], None] | None = None
        self._last_flush = 0.0
        self._progress = 0.0
        self._message = ""
        self._logs: list[str] = []

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled()

    def update(self, progress: float | None = None, message: str | None = None, force: bool = False) -> None:
        if progress is not None:
            self._progress = max(0.0, min(1.0, progress))
        if message is not None:
            self._message = message
        now = time.monotonic()
        if force or now - self._last_flush > 0.4:
            self._last_flush = now
            self.manager.persist(self.job_id, progress=self._progress, message=self._message, logs=self._logs)

    def log(self, line: str) -> None:
        self._logs.append(line.rstrip())
        self.update()


Handler = Callable[[JobContext], Awaitable[dict]]


class JobManager:
    def __init__(self) -> None:
        self.handlers: dict[str, tuple[Handler, bool]] = {}
        self.gpu_lock = asyncio.Lock()
        self.contexts: dict[int, JobContext] = {}
        self.tasks: dict[int, asyncio.Task] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def register(self, kind: str, gpu: bool = True) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self.handlers[kind] = (fn, gpu)
            return fn

        return deco

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        with Session(engine) as s:
            for job in s.exec(select(Job).where(Job.status.in_(["queued", "running"]))):
                job.status = "failed"
                job.error = "Interrupted by server restart"
                job.finished_at = utcnow()
                s.add(job)
            s.commit()

    def _emit(self, job: Job) -> None:
        if self.loop is None:
            return
        msg = {"type": "job", "job": job_to_dict(job)}
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(hub.broadcast(msg))
        else:
            asyncio.run_coroutine_threadsafe(hub.broadcast(msg), self.loop)

    def persist(self, job_id: int, logs: list[str] | None = None, **fields: Any) -> Job | None:
        with Session(engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                return None
            for k, v in fields.items():
                setattr(job, k, v)
            if logs is not None:
                job.logs = "\n".join(logs)[-MAX_LOG_CHARS:]
            s.add(job)
            s.commit()
            s.refresh(job)
            self._emit(job)
            return job

    async def submit(self, kind: str, payload: dict, message: str = "Queued") -> Job:
        if kind not in self.handlers:
            raise ValueError(f"Unknown job kind {kind}")
        with Session(engine) as s:
            job = Job(kind=kind, payload=payload, message=message)
            s.add(job)
            s.commit()
            s.refresh(job)
        ctx = JobContext(self, job.id, payload)
        self.contexts[job.id] = ctx
        self.tasks[job.id] = asyncio.create_task(self._run(job.id, ctx))
        self._emit(job)
        return job

    async def _run(self, job_id: int, ctx: JobContext) -> None:
        handler, gpu = self.handlers[self.persist(job_id).kind]  # type: ignore[union-attr]
        try:
            if gpu:
                async with self.gpu_lock:
                    ctx.check_cancelled()
                    self.persist(job_id, status="running", message="Starting")
                    result = await handler(ctx)
            else:
                self.persist(job_id, status="running", message="Starting")
                result = await handler(ctx)
            self.persist(
                job_id,
                logs=ctx._logs,
                status="done",
                progress=1.0,
                message="Done",
                result=result or {},
                finished_at=utcnow(),
            )
        except (JobCancelled, asyncio.CancelledError):
            self.persist(job_id, logs=ctx._logs, status="cancelled", message="Cancelled", finished_at=utcnow())
        except Exception as exc:
            if ctx.cancelled:
                self.persist(job_id, logs=ctx._logs, status="cancelled", message="Cancelled", finished_at=utcnow())
                return
            log.exception("Job %s failed", job_id)
            ctx._logs.append(traceback.format_exc())
            self.persist(
                job_id,
                logs=ctx._logs,
                status="failed",
                error=str(exc) or exc.__class__.__name__,
                message="Failed",
                finished_at=utcnow(),
            )
        finally:
            self.contexts.pop(job_id, None)
            self.tasks.pop(job_id, None)

    def cancel(self, job_id: int) -> bool:
        ctx = self.contexts.get(job_id)
        if ctx is None:
            return False
        ctx.cancel_event.set()
        if ctx.on_cancel:
            try:
                ctx.on_cancel()
            except Exception:
                log.exception("on_cancel hook failed for job %s", job_id)
        task = self.tasks.get(job_id)
        with Session(engine) as s:
            job = s.get(Job, job_id)
            queued = job is not None and job.status == "queued"
        # Queued jobs are waiting on the GPU lock and can be cancelled outright;
        # running jobs stop cooperatively via the cancel event.
        if task and queued:
            task.cancel()
        return True


manager = JobManager()
