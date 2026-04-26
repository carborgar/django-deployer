import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import App, Deployment

router = APIRouter(prefix="/logs")

APPS_DIR = os.environ.get("DEPLOYER_APPS_DIR", "/opt/apps")


@router.get("/deployment/{deployment_id}/stream")
async def stream_deployment_log(deployment_id: int, db: Session = Depends(get_db)):
    """SSE: hace streaming del log de un deployment en curso o completado."""
    d = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not d:
        raise HTTPException(status_code=404)

    log_path = os.path.join(APPS_DIR, d.app.name, "logs", f"deploy-{deployment_id}.log")

    async def event_generator():
        if not os.path.exists(log_path):
            yield f"data: Esperando log...\n\n"
            await asyncio.sleep(1)

        pos = 0
        while True:
            db.refresh(d)
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    f.seek(pos)
                    chunk = f.read()
                    if chunk:
                        for line in chunk.splitlines():
                            yield f"data: {line}\n\n"
                        pos = f.tell()

            if d.status in ("success", "failed"):
                yield "data: [FIN]\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/app/{app_id}/tail")
async def tail_app_log(app_id: int, lines: int = 100, db: Session = Depends(get_db)):
    """Devuelve las últimas N líneas del log de gunicorn de la app."""
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)

    log_path = os.path.join(APPS_DIR, app.name, "logs", "app.log")
    if not os.path.exists(log_path):
        return {"lines": []}

    with open(log_path, "r") as f:
        all_lines = f.readlines()

    return {"lines": [l.rstrip() for l in all_lines[-lines:]]}
