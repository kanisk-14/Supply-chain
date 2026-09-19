"""Service-layer transaction boundary.

Stock mutations and master-data writes are units of work owned by the *service*
layer: repositories receive a ``Session`` and never commit, and services decide
the commit point. The request-scoped session autobegins on first read (e.g. the
``get_current_user`` authentication lookup), so ``Session.begin()`` cannot be
re-entered; instead services wrap their workflow with :func:`transaction`, which
commits on success and rolls back the entire unit of work on any failure.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def transaction(db: Session) -> Iterator[Session]:
    """Commit on success, roll back everything on failure.

    A failed write workflow therefore never publishes a partial effect (e.g. a
    transfer that decremented the source but crashed before the destination).
    """
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise