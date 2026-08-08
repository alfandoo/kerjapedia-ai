from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    pool_timeout=settings.database_pool_timeout_seconds,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_session() -> Session:
    return SessionLocal()


def ensure_schema() -> None:
    from app.db.base import Base
    from app.models import business as _business_models  # noqa: F401
    from app.models import ingestion as _ingestion_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
