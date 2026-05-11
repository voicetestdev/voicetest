"""DuckDB-specific session handling.

DuckDB is an embedded, in-process database. voicetest shares a singleton
SQLAlchemy Session across request threads because pool_size=1 makes
per-request sessions deadlock waiting for the pool's single connection.

SQLAlchemy Session is not thread-safe, so concurrent users of the
singleton produce ``InvalidRequestError: This session is provisioning a
new connection; concurrent operations are not permitted`` — and under
load can segfault DuckDB's C extension.

This module patches every mutating Session method to serialize on a
single RLock. Applied only to DuckDB sessions; Postgres uses transient
sessions and does not need the lock.
"""

from __future__ import annotations

import functools
import threading

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker


_SESSION_LOCK = threading.RLock()

# Session methods that mutate state or hit the DB. Patching these on the
# instance funnels every access path through the lock — including Query
# objects returned by session.query(...), which hold a back-reference to
# the underlying Session and would bypass a __getattr__ proxy when they
# later call session.execute() internally.
_LOCKED_METHODS = (
    "execute",
    "scalar",
    "scalars",
    "get",
    "add",
    "add_all",
    "delete",
    "merge",
    "flush",
    "refresh",
    "commit",
    "rollback",
    "close",
    "query",
)


def wrap_session(session: Session) -> Session:
    """Patch a Session's mutating methods so they serialize on _SESSION_LOCK."""
    for name in _LOCKED_METHODS:
        original = getattr(session, name, None)
        if original is None:
            continue

        @functools.wraps(original)
        def locked(*args, _original=original, **kwargs):
            with _SESSION_LOCK:
                return _original(*args, **kwargs)

        setattr(session, name, locked)
    return session


class DuckDBSessionMaker(sessionmaker):
    """sessionmaker that returns thread-safe sessions for DuckDB.

    Identical to the base sessionmaker except every returned Session is
    instrumented with the lock-wrapping above before being handed out.
    """

    def __call__(self, **kwargs) -> Session:
        return wrap_session(super().__call__(**kwargs))
