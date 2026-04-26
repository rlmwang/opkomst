import os
from contextlib import asynccontextmanager

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .migrate import run_migrations
from .seed import run as run_seed
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import events as events_router
from .routers import feedback as feedback_router
from .routers import signups as signups_router
from .routers import webhooks as webhooks_router
from .services import feedback_worker

logger = structlog.get_logger()

run_migrations()
run_seed()

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if os.environ.get("DISABLE_SCHEDULER") != "1":
        _scheduler.add_job(feedback_worker.run_once, "interval", hours=1, id="feedback_sweep")
        _scheduler.start()
        logger.info("scheduler_started")
    try:
        yield
    finally:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)


app = FastAPI(title="Opkomst", version="0.1.0", lifespan=_lifespan)

# CORS — dev frontend on 5173. In prod the frontend is served from the
# same origin so this becomes a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(events_router.router)
app.include_router(signups_router.router)
app.include_router(feedback_router.router)
app.include_router(webhooks_router.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
