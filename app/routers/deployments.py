from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Deployment

router = APIRouter(prefix="/deployments")
templates = Jinja2Templates(directory="app/templates")


@router.get("/{deployment_id}", response_class=HTMLResponse)
async def deployment_detail(deployment_id: int, request: Request, db: Session = Depends(get_db)):
    d = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not d:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("deployment_detail.html", {"request": request, "deployment": d})
