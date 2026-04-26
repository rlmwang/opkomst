"""Auto-run Alembic migrations on app startup."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    cfg_path = Path(__file__).parent / "alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")
