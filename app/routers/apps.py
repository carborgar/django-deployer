from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import os
import logging

from app.database import get_db
from app.models import App, DeployCommand, EnvVar
from app.crypto import encrypt
from app.services.env_parser import parse_env_text
from app.services import deployer, nginx_manager, systemd_manager
from app.templating import templates

router = APIRouter()
_ROOT = os.environ.get("DEPLOYER_ROOT_PATH", "")
logger = logging.getLogger(__name__)


def _new_app_form_context(request: Request, error: str | None = None, form_data: dict | None = None):
    return {
        "request": request,
        "app": None,
        "error": error,
        "form_data": form_data or {},
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    apps = db.query(App).order_by(App.name).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "apps": apps})


@router.get("/apps/new", response_class=HTMLResponse)
async def new_app_form(request: Request):
    return templates.TemplateResponse("app_form.html", _new_app_form_context(request))


@router.post("/apps/new")
async def create_app(
    request: Request,
    name: str = Form(...),
    repo_url: str = Form(...),
    branch: str = Form("main"),
    path_prefix: str = Form(...),
    port: int = Form(...),
    github_token: str = Form(""),
    env_text: str = Form(""),
    db: Session = Depends(get_db),
):
    form_data = {
        "name": name,
        "repo_url": repo_url,
        "branch": branch,
        "path_prefix": path_prefix,
        "port": str(port),
        "env_text": env_text,
    }

    if db.query(App).filter(App.name == name).first():
        return templates.TemplateResponse(
            "app_form.html",
            _new_app_form_context(request, f"Ya existe una app con el nombre '{name}'", form_data),
            status_code=400,
        )

    env_pairs, invalid_lines = parse_env_text(env_text)
    if invalid_lines:
        preview = ", ".join(invalid_lines[:3])
        more = "" if len(invalid_lines) <= 3 else f" (+{len(invalid_lines) - 3} más)"
        return templates.TemplateResponse(
            "app_form.html",
            _new_app_form_context(request, f"Formato .env inválido en: {preview}{more}", form_data),
            status_code=400,
        )

    encrypted_token = encrypt(github_token) if github_token else None

    app = App(
        name=name,
        repo_url=repo_url,
        branch=branch,
        path_prefix=path_prefix.strip("/"),
        port=port,
        github_token=encrypted_token,
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    # Añadir comandos por defecto
    defaults = [
        DeployCommand(app_id=app.id, order=0, command="pip install -r requirements.txt"),
        DeployCommand(app_id=app.id, order=1, command="python manage.py migrate --noinput"),
        DeployCommand(app_id=app.id, order=2, command="python manage.py collectstatic --noinput"),
    ]
    db.add_all(defaults)

    for key, value in env_pairs:
        db.add(EnvVar(app_id=app.id, key=key, value_encrypted=encrypt(value)))

    db.commit()

    if not systemd_manager.create_service(app):
        logger.warning(f"No se pudo crear/activar systemd para app {app.name}")

    nginx_manager.generate_and_reload(app)

    return RedirectResponse(url=f"{_ROOT}/apps/{app.id}", status_code=303)


@router.get("/apps/{app_id}", response_class=HTMLResponse)
async def app_detail(app_id: int, request: Request, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    deployments = app.deployments[-10:][::-1]
    return templates.TemplateResponse(
        "app_detail.html",
        {"request": request, "app": app, "deployments": deployments},
    )


@router.get("/apps/{app_id}/edit", response_class=HTMLResponse)
async def edit_app_form(app_id: int, request: Request, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("app_form.html", {"request": request, "app": app})


@router.post("/apps/{app_id}/edit")
async def edit_app(
    app_id: int,
    request: Request,
    repo_url: str = Form(...),
    branch: str = Form("main"),
    path_prefix: str = Form(...),
    port: int = Form(...),
    github_token: str = Form(""),
    active: bool = Form(False),
    db: Session = Depends(get_db),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)

    app.repo_url = repo_url
    app.branch = branch
    app.path_prefix = path_prefix.strip("/")
    app.port = port
    app.active = active
    if github_token:
        app.github_token = encrypt(github_token)

    db.commit()
    if not systemd_manager.create_service(app):
        logger.warning(f"No se pudo actualizar systemd para app {app.name}")
    nginx_manager.generate_and_reload(app)
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}", status_code=303)


@router.post("/apps/{app_id}/delete")
async def delete_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    if not systemd_manager.remove_service(app):
        logger.warning(f"No se pudo eliminar systemd para app {app.name}")
    nginx_manager.remove(app)
    db.delete(app)
    db.commit()
    return RedirectResponse(url=f"{_ROOT}/", status_code=303)


@router.post("/apps/{app_id}/deploy")
async def manual_deploy(app_id: int, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    import asyncio
    asyncio.create_task(deployer.deploy_app(app_id))
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}", status_code=303)


@router.post("/apps/{app_id}/restart")
async def restart_app(app_id: int, db: Session = Depends(get_db)):
    """Reinicia el proceso gunicorn sin hacer un deploy completo."""
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    import subprocess
    service = f"django-{app.name}"
    result = subprocess.run(
        ["sudo", "-n", "systemctl", "restart", service],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"Restart manual de {service} falló: {result.stderr.strip()}")
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}", status_code=303)


@router.get("/apps/{app_id}/status")
async def app_status(app_id: int, db: Session = Depends(get_db)):
    """Endpoint ligero para HTMX polling de estado."""
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    last = app.deployments[-1] if app.deployments else None
    return {
        "deployed_commit": app.deployed_commit,
        "last_status": last.status if last else "none",
        "last_checked_at": app.last_checked_at.isoformat() if app.last_checked_at else None,
    }
