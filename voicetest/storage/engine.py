"""SQLAlchemy engine factory for voicetest storage."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from voicetest.config import get_db_path
from voicetest.storage.models import Base


def create_db_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine.

    If url is None, uses DuckDB at the default path from config.
    For PostgreSQL (SaaS), pass a connection URL like:
        postgresql://user:pass@host/db

    Args:
        url: Database connection URL. If None, uses DuckDB at default path.

    Returns:
        SQLAlchemy Engine instance with schema initialized.
    """
    if url is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"duckdb:///{db_path}"

    engine = create_engine(url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine.

    Args:
        engine: SQLAlchemy Engine instance.

    Returns:
        A sessionmaker that creates Session instances.
    """
    return sessionmaker(bind=engine)
