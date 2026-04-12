"""Alembic environment — sync engine; use postgresql:// or set ALEMBIC_DATABASE_URL."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

from app.database.models import Base


def _merge_backend_dotenv_into_environ() -> None:
    """Load `apps/backend/.env` into os.environ for keys not already set (cwd-independent)."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ[key] = val

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_database_url() -> str:
    """Resolve DB URL: shell / backend `.env`, then full app settings (Pydantic)."""
    _merge_backend_dotenv_into_environ()
    url = (os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        try:
            from app.core.config import get_settings

            url = (get_settings().database_url or "").strip()
        except Exception:
            url = ""
    if "+asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("sqlite+aiosqlite"):
        url = url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if not url:
        raise RuntimeError(
            "No database URL for Alembic. Export DATABASE_URL or ALEMBIC_DATABASE_URL, "
            "or run from `apps/backend` so `.env` is found (same as uvicorn), or pass "
            "`alembic -x sqlalchemy.url=postgresql://... upgrade head`."
        )
    return _postgresql_url_with_sync_driver(url)


def _postgresql_url_with_sync_driver(url: str) -> str:
    """Alembic uses a sync engine; pick psycopg2 or psycopg3 if URL has no +driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    scheme_part, sep, rest = url.partition("://")
    if sep != "://" or not rest:
        return url
    if not scheme_part.startswith("postgresql"):
        return url  # sqlite, mysql, etc.
    if "+" in scheme_part:
        return url  # e.g. postgresql+psycopg2://
    try:
        import psycopg2  # noqa: F401
        return url
    except ImportError:
        pass
    try:
        import psycopg  # noqa: F401
        return f"postgresql+psycopg://{rest}"
    except ImportError:
        raise RuntimeError(
            "Alembic needs a synchronous PostgreSQL driver (asyncpg is not enough). "
            "From your venv run: pip install psycopg2-binary   "
            "or: pip install 'psycopg[binary]'"
        ) from None


def run_migrations_offline() -> None:
    url = _sync_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_sync_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
