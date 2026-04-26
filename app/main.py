import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.models import init_db
from app.routers import apps, deployments, envvars, commands, logs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")

    from app.services.poller import poll_all_apps
    scheduler.add_job(poll_all_apps, "interval", seconds=60, id="github_poller", replace_existing=True)
    scheduler.start()
    logger.info("Poller scheduler started (interval: 60s)")

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title="Django Deployer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(apps.router)
app.include_router(deployments.router)
app.include_router(envvars.router)
app.include_router(commands.router)
app.include_router(logs.router)
