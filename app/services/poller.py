"""
Poller de GitHub: cada 60s comprueba el último commit de cada app activa.
Si el commit difiere del desplegado, lanza un deploy automático.
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.models import App, engine

logger = logging.getLogger(__name__)


async def poll_all_apps():
    logger.info("Poller: comprobando repos...")
    with Session(engine) as db:
        apps = db.query(App).filter(App.active == True).all()
        app_ids = [a.id for a in apps]

    for app_id in app_ids:
        try:
            await _check_app(app_id)
        except Exception as e:
            logger.error(f"Error poller app {app_id}: {e}")


async def _check_app(app_id: int):
    from app.services.deployer import deploy_app
    from app.crypto import decrypt

    with Session(engine) as db:
        app = db.query(App).filter(App.id == app_id).first()
        if not app:
            return

        owner, repo = _parse_repo(app.repo_url)
        if not owner or not repo:
            logger.warning(f"No se pudo parsear repo_url: {app.repo_url}")
            return

        token = decrypt(app.github_token) if app.github_token else None
        headers = {"Authorization": f"token {token}"} if token else {}

        async with httpx.AsyncClient(timeout=10) as client:
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{app.branch}"
            resp = await client.get(url, headers=headers)

        app.last_checked_at = datetime.now(timezone.utc)

        if resp.status_code != 200:
            logger.warning(f"GitHub API {resp.status_code} para {owner}/{repo}")
            db.commit()
            return

        latest_sha = resp.json()["sha"]

        if latest_sha != app.deployed_commit:
            logger.info(f"Nuevo commit en {app.name}: {latest_sha[:7]} (antes: {app.deployed_commit})")
            db.commit()
            asyncio.create_task(deploy_app(app_id, latest_sha))
        else:
            logger.debug(f"{app.name}: sin cambios ({latest_sha[:7]})")
            db.commit()


def _parse_repo(url: str) -> tuple[str, str]:
    """Extrae owner y repo de una URL de GitHub."""
    url = url.rstrip("/").removesuffix(".git")
    parts = url.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "", ""
