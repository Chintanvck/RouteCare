"""
RouteCare AI - Alembic migration environment.

The database URL comes from app settings (which reads DATABASE_URL
from the environment) rather than a hardcoded value in alembic.ini,
so migrations always target the same database as the running app.

target_metadata points at app.database.base.Base, so as soon as
models are added (Phase 1's database implementation), `alembic
revision --autogenerate` will pick them up automatically.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Import models here so they register with Base.metadata before
# autogenerate runs.
import app.models  # noqa: E402,F401
from alembic import context
from app.core.config import settings
from app.database.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
