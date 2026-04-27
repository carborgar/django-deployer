from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import os

from app.crypto import encrypt, decrypt
from app.database import get_db
from app.models import App, EnvVar
from app.services.env_parser import is_valid_env_key, parse_env_text
from app.templating import templates

router = APIRouter(prefix="/apps/{app_id}/env")
_ROOT = os.environ.get("DEPLOYER_ROOT_PATH", "")


@router.get("/", response_class=HTMLResponse)
async def list_env(app_id: int, request: Request, db: Session = Depends(get_db)):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    env_vars = [(v.id, v.key, decrypt(v.value_encrypted)) for v in app.env_vars]
    return templates.TemplateResponse("envvars.html", {"request": request, "app": app, "env_vars": env_vars})


@router.post("/add")
async def add_env(
    app_id: int,
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)
    key = key.strip()
    if not is_valid_env_key(key):
        raise HTTPException(status_code=400, detail="Clave de variable inválida")
    existing = db.query(EnvVar).filter(EnvVar.app_id == app_id, EnvVar.key == key).first()
    if existing:
        existing.value_encrypted = encrypt(value)
    else:
        db.add(EnvVar(app_id=app_id, key=key, value_encrypted=encrypt(value)))
    db.commit()
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}/env/", status_code=303)


@router.post("/bulk")
async def bulk_env(
    app_id: int,
    env_text: str = Form(...),
    db: Session = Depends(get_db),
):
    """Parsea un bloque estilo .env y upserta todas las variables."""
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404)

    pairs, _ = parse_env_text(env_text)
    for key, value in pairs:
        existing = db.query(EnvVar).filter(EnvVar.app_id == app_id, EnvVar.key == key).first()
        if existing:
            existing.value_encrypted = encrypt(value)
        else:
            db.add(EnvVar(app_id=app_id, key=key, value_encrypted=encrypt(value)))

    db.commit()
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}/env/", status_code=303)


@router.post("/{var_id}/delete")
async def delete_env(app_id: int, var_id: int, db: Session = Depends(get_db)):
    var = db.query(EnvVar).filter(EnvVar.id == var_id, EnvVar.app_id == app_id).first()
    if not var:
        raise HTTPException(status_code=404)
    db.delete(var)
    db.commit()
    return RedirectResponse(url=f"{_ROOT}/apps/{app_id}/env/", status_code=303)
