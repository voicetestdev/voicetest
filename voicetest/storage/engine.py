"""SQLAlchemy engine factory for voicetest storage."""

import logging

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from voicetest.config import get_db_path
from voicetest.storage.models import Base


logger = logging.getLogger(__name__)

# Ordered list of schema migrations. Each is (version, description, sql, verify_sql).
# sql can be a single string or a list of strings (executed in order).
# Append-only — never reorder or remove entries. Version numbers must be sequential.
# verify_sql: a SELECT that returns a row if the migration was truly applied.
_MIGRATIONS: list[tuple[int, str, str | list[str], str]] = [
    (
        1,
        "Add tests_paths to agents",
        "ALTER TABLE agents ADD COLUMN tests_paths JSON",
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'agents' AND column_name = 'tests_paths'",
    ),
    (
        2,
        "Add call_id to results and make test_case_id nullable",
        [
            "ALTER TABLE results ADD COLUMN call_id VARCHAR",
            "ALTER TABLE results ALTER COLUMN test_case_id DROP NOT NULL",
        ],
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'results' AND column_name = 'call_id'",
    ),
]


def _ensure_schema_version_table(conn) -> None:
    """Create the schema_version table if it doesn't exist."""
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, "
            "description VARCHAR NOT NULL, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
    )


def _get_current_version(conn) -> int:
    """Get the highest applied migration version, or 0 if none."""
    result = conn.execute(text("SELECT COALESCE(MAX(version), 0) FROM schema_version"))
    return result.scalar()


def _stamp_current(conn) -> None:
    """Mark all migrations as applied without running them.

    Used on fresh databases where create_all already built the full schema.
    """
    for version, description, _sql, _verify in _MIGRATIONS:
        conn.execute(
            text("INSERT INTO schema_version (version, description) VALUES (:v, :d)"),
            {"v": version, "d": description},
        )


def _has_table(conn, table_name: str) -> bool:
    """Check if a table exists via INFORMATION_SCHEMA."""
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
        {"t": table_name},
    )
    return result.fetchone() is not None


def _migrate_schema(engine: Engine) -> None:
    """Run pending schema migrations.

    Tracks applied migrations in a schema_version table. Each migration runs
    exactly once, in order. Supports arbitrary SQL — not just ADD COLUMN.

    Three cases:
    - Fresh DB (no data tables): stamp all migrations, create_all handles the rest.
    - Old DB (data tables exist, no schema_version): run all pending migrations.
    - Up-to-date DB (schema_version exists with entries): skip already-applied migrations.
    """
    with engine.begin() as conn:
        has_data_tables = _has_table(conn, "agents")

        _ensure_schema_version_table(conn)

        if not has_data_tables:
            logger.info("Fresh database — stamping %d migration(s)", len(_MIGRATIONS))
            _stamp_current(conn)
            return

        # Existing DB — run any pending migrations
        current = _get_current_version(conn)

        # Verify applied migrations are real (detect phantom stamps)
        for version, description, _sql, verify_sql in _MIGRATIONS:
            if version > current:
                break
            result = conn.execute(text(verify_sql))
            if result.fetchone() is None:
                logger.warning(
                    "Phantom migration %d detected (%s) — re-running",
                    version,
                    description,
                )
                conn.execute(
                    text("DELETE FROM schema_version WHERE version = :v"),
                    {"v": version},
                )
                current = _get_current_version(conn)

        pending = [m for m in _MIGRATIONS if m[0] > current]

        if not pending:
            logger.info("Schema up to date at version %d", current)
            return

        logger.info("Running %d pending migration(s) from version %d", len(pending), current)
        for version, description, sql, _verify in pending:
            logger.info("Migration %d: %s", version, description)
            statements = sql if isinstance(sql, list) else [sql]
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_version (version, description) VALUES (:v, :d)"),
                {"v": version, "d": description},
            )
        logger.info("Migrations complete — now at version %d", pending[-1][0])


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
    # Migrate BEFORE create_all so ALTERs run against the existing schema
    _migrate_schema(engine)
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
