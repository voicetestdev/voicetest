"""DuckDB connection and schema management."""

import duckdb

from voicetest.config import get_db_path


def create_connection() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection.

    Use the DI container to get the singleton connection instance.
    This function is registered as a factory in container.py.
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Initialize database schema with all required tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_path TEXT,
            graph_json TEXT,
            metrics_config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_cases (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            user_prompt TEXT NOT NULL,
            metrics TEXT,
            dynamic_variables TEXT,
            tool_mocks TEXT,
            type TEXT DEFAULT 'llm',
            llm_model TEXT,
            includes TEXT,
            excludes TEXT,
            patterns TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            agent_id TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            test_case_id TEXT NOT NULL,
            test_name TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms INTEGER,
            turn_count INTEGER,
            end_reason TEXT,
            error_message TEXT,
            transcript_json TEXT,
            metrics_json TEXT,
            nodes_visited TEXT,
            tools_called TEXT,
            models_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
