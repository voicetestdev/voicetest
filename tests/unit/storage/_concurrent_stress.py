"""Subprocess script: hammer DuckDB with concurrent reads and writes.

Used by test_engine.py::TestDuckDBConcurrency. Runs in a subprocess so a
segfault doesn't kill the test runner.

The engine factory uses QueuePool(pool_size=1, max_overflow=0) to serialize
access — only one thread holds the connection at a time. Without this,
concurrent access on a shared DuckDB connection segfaults or raises
transaction errors.
"""

import sys
import threading

from sqlalchemy import text

from voicetest.storage.engine import create_db_engine


def main():
    db_path = sys.argv[1]
    engine = create_db_engine(f"duckdb:///{db_path}")

    # Seed data
    with engine.begin() as conn:
        for i in range(10):
            conn.execute(
                text(
                    "INSERT INTO agents (id, name, source_type, created_at, updated_at) "
                    "VALUES (:id, :name, 'test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": f"agent-{i}", "name": f"Agent {i}"},
            )

    errors = []
    barrier = threading.Barrier(8)

    def reader(thread_id):
        try:
            barrier.wait(timeout=5)
            for _ in range(100):
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT id, name FROM agents"))
                    _ = result.fetchall()
        except Exception as e:
            errors.append(f"reader-{thread_id}: {e}")

    def writer(thread_id):
        try:
            barrier.wait(timeout=5)
            for j in range(100):
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO runs (id, agent_id, started_at) "
                            "VALUES (:id, 'agent-0', CURRENT_TIMESTAMP)"
                        ),
                        {"id": f"run-{thread_id}-{j}"},
                    )
        except Exception as e:
            errors.append(f"writer-{thread_id}: {e}")

    threads = []
    for i in range(4):
        threads.append(threading.Thread(target=reader, args=(i,)))
    for i in range(4):
        threads.append(threading.Thread(target=writer, args=(i,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    if errors:
        print(f"Errors: {errors}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
