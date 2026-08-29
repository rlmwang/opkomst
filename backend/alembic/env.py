from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend import models  # noqa: F401, E402
from backend.config import settings  # noqa: E402

# Import models so Alembic sees them.
from backend.database import Base  # noqa: E402
from backend.models.archive import archive_metadata  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull DATABASE_URL from settings (overrides any value in alembic.ini).
config.set_main_option("sqlalchemy.url", settings.database_url)

# Both schemas: the live tables, and the archive twins generated from
# them. Autogenerate then emits a column change for a table and its twin
# from the one model definition, which is the whole point of generating
# them — a hand-written mirror drifts the first time somebody forgets.
target_metadata = [Base.metadata, archive_metadata]


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
