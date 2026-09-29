from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from ..db import get_session
from ..jobs import hub, job_to_dict, manager
from ..models import Job
from ..services.crud import get_or_404

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
def list_jobs(limit: int = 50, session: Session = Depends(get_session)) -> list[dict]:
    jobs = session.exec(select(Job).order_by(Job.id.desc()).limit(limit))
    return [job_to_dict(j) for j in jobs]


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    job = get_or_404(session, Job, job_id)
    return job.model_dump(mode="json")


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int) -> dict:
    return {"ok": manager.cancel(job_id)}


@router.delete("/api/jobs")
def clear_finished(session: Session = Depends(get_session)) -> dict:
    for job in session.exec(select(Job).where(Job.status.in_(["done", "failed", "cancelled"]))):
        session.delete(job)
    session.commit()
    return {"ok": True}


@router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)
