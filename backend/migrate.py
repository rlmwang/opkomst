"""Auto-run Alembic migrations on app startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import settings


def run_migrations() -> None:
    cfg_path = Path(__file__).parent / "alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")
