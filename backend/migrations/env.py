from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import backend.app.models  # noqa: F401
from backend.app.config import get_settings
from backend.app.db import Base, ensure_sqlite_parent
from backend.app.models.types import UTCDateTime

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
ensure_sqlite_parent(settings.database_url)
target_metadata = Base.metadata


def render_item(type_: str, obj, autogen_context):
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.String(length=27)"
    return False


def include_object(obj, name: str, type_: str, reflected: bool, compare_to) -> bool:
    # SQLite can add this nullable reference column in place, but its inspector
    # cannot reflect the inline FK name/options consistently. The populated-DB
    # migration test verifies its target and RESTRICT action with PRAGMA.
    if settings.database_url.startswith("sqlite:") and type_ == "foreign_key_constraint":
        table = getattr(obj, "table", None)
        constrained = [column.name for column in getattr(obj, "columns", ())]
        if table is not None and table.name == "contests" and constrained == ["series_id"]:
            return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
        include_object=include_object,
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
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            if settings.database_url != "sqlite:///:memory:":
                connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_item=render_item,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
        # Explicitly persist Alembic's version-row DML under sqlite3's legacy transaction mode.
        if connection.in_transaction():
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
