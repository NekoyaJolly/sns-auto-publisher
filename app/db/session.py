from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings, get_settings
from app.db.models import Base


def ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database:
        return
    if url.database == ":memory:":
        return
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)


def create_app_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    ensure_sqlite_parent(resolved_settings.database_url)
    connect_args = {"check_same_thread": False} if resolved_settings.database_url.startswith("sqlite") else {}
    return create_engine(resolved_settings.database_url, connect_args=connect_args, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_post_job_columns(engine)


def ensure_sqlite_post_job_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "post_jobs" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("post_jobs")}
    required_columns = {
        "genre_key": "VARCHAR(255)",
        "genre_label": "VARCHAR(255)",
        "caption_instruction": "TEXT",
    }
    with engine.begin() as connection:
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE post_jobs ADD COLUMN {column_name} {column_type}"))


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
