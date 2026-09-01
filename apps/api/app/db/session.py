from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    pool_timeout=settings.database_pool_timeout_seconds,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
EXPECTED_SCHEMA_REVISION = "20260901_0006"


def create_session() -> Session:
    return SessionLocal()


def assert_schema_current() -> None:
    try:
        with engine.connect() as connection:
            current_revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    except Exception as exc:
        raise RuntimeError(
            "Database schema revision is unavailable; run `python -m alembic upgrade head`."
        ) from exc
    if current_revision != EXPECTED_SCHEMA_REVISION:
        raise RuntimeError(
            "Database schema is out of date "
            f"(current={current_revision or 'none'}, expected={EXPECTED_SCHEMA_REVISION}); "
            "run `python -m alembic upgrade head`."
        )
