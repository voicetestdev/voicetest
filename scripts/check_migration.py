"""Diagnostic script to verify migration state on the real DB."""

from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy import text

from voicetest.storage.engine import _migrate_schema


def main():
    db_path = Path(".voicetest/data.duckdb")
    if not db_path.exists():
        print(f"DB not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Opening {db_path} ({db_path.stat().st_size} bytes)", file=sys.stderr)

    wal_path = Path(f"{db_path}.wal")
    if wal_path.exists():
        print(f"WAL file exists: {wal_path.stat().st_size} bytes", file=sys.stderr)

    engine = create_engine(f"duckdb:///{db_path}", echo=False)

    with engine.begin() as conn:
        # Check tables
        result = conn.execute(text("SELECT table_name FROM information_schema.tables"))
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables: {tables}", file=sys.stderr)

        # Check if agents table has tests_paths
        result = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'agents'")
        )
        columns = [row[0] for row in result.fetchall()]
        print(f"Agents columns: {columns}", file=sys.stderr)

        has_tests_paths = "tests_paths" in columns
        print(f"Has tests_paths: {has_tests_paths}", file=sys.stderr)

        # Check schema_version
        has_sv = "schema_version" in tables
        print(f"Has schema_version table: {has_sv}", file=sys.stderr)

        if has_sv:
            result = conn.execute(text("SELECT version, description FROM schema_version"))
            rows = result.fetchall()
            print(f"Schema versions: {rows}", file=sys.stderr)

            # Detect phantom migration: version recorded but column missing
            if not has_tests_paths and any(v == 1 for v, _ in rows):
                print(
                    "\nPHANTOM MIGRATION DETECTED: version 1 recorded but "
                    "tests_paths column missing. Fixing...",
                    file=sys.stderr,
                )
                conn.execute(text("DELETE FROM schema_version WHERE version = 1"))
                print("Deleted phantom version 1 entry", file=sys.stderr)
        else:
            print("No schema_version table — migration has never run", file=sys.stderr)

    # Now try running the actual migration
    print("\n--- Running migration ---", file=sys.stderr)
    _migrate_schema(engine)
    print("--- Migration complete ---", file=sys.stderr)

    # Verify
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'agents'")
        )
        columns = [row[0] for row in result.fetchall()]
        print(f"Agents columns after migration: {columns}", file=sys.stderr)

        has_tests_paths = "tests_paths" in columns
        if has_tests_paths:
            print("SUCCESS: tests_paths column exists", file=sys.stderr)
        else:
            print("FAILURE: tests_paths column still missing", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
