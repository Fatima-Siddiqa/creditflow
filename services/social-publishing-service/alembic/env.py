from logging.config import fileConfig
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.db import Base
from app.models.social import SocialConnection, PublishJob, PostMedia, ProcessedEvent
from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table_schema=settings.db_schema,
        include_schemas=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # version_table_schema alone isn't enough on a genuinely fresh
        # database: Alembic creates alembic_version in that schema BEFORE
        # running any migration's upgrade() function, so a migration-body
        # `CREATE SCHEMA IF NOT EXISTS` (see versions/dad112290312_*.py)
        # runs too late to help. Create it here instead, ahead of
        # context.configure.
        connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {settings.db_schema}")
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=settings.db_schema,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()