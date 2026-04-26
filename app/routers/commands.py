from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os

from app.database import get_db
from app.models import App, DeployCommand

router = APIRouter(prefix="/apps/{app_id}/commands")
templates = Jinja2Templates(directory="app/templates")
_ROOT = os.environ.get("DEPLOYER_ROOT_PATH", "")


@router.get("/", response_class=HTMLResponse)
async def list_commands(app_id: int, request: Request, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("commands.html", {"request": request, "app": app})


@router.post("/add")
async def add_command(
    app_id: int,
    command: str = Form(...),
    order: int = Form(0),
    db: Session = Depends(get_db),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    db.add(DeployCommand(app_id=app_id, command=command, order=order))
    db.commit()
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}/commands/", status_code=303)


@router.post("/{cmd_id}/delete")
async def delete_command(app_id: int, cmd_id: int, db: Session = Depends(get_db)):
    cmd = db.query(DeployCommand).filter(DeployCommand.id == cmd_id, DeployCommand.app_id == app_id).first()
    if not cmd:
        raise HTTPException(status_code=404)
    db.delete(cmd)
    db.commit()
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}/commands/", status_code=303)


@router.post("/{cmd_id}/move")
async def move_command(
    app_id: int,
    cmd_id: int,
    direction: str = Form(...),
    db: Session = Depends(get_db),
):
    """Mueve un comando arriba o abajo intercambiando el order con su vecino."""
    cmd = db.query(DeployCommand).filter(DeployCommand.id == cmd_id, DeployCommand.app_id == app_id).first()
    if not cmd:
        raise HTTPException(status_code=404)

    all_cmds = db.query(DeployCommand).filter(DeployCommand.app_id == app_id).order_by(DeployCommand.order).all()
    idx = next((i for i, c in enumerate(all_cmds) if c.id == cmd_id), None)

    if direction == "up" and idx > 0:
        all_cmds[idx].order, all_cmds[idx - 1].order = all_cmds[idx - 1].order, all_cmds[idx].order
    elif direction == "down" and idx < len(all_cmds) - 1:
        all_cmds[idx].order, all_cmds[idx + 1].order = all_cmds[idx + 1].order, all_cmds[idx].order

    db.commit()
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}/commands/", status_code=303)
