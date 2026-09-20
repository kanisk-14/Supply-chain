"""Lightweight scheduled alert evaluator.

A single in-process polling loop (no Celery/Redis): every
``SCHEDULER_INTERVAL_SECONDS`` it runs :func:`app.jobs.service.run_overdue_check`,
which reconciles SHIPMENT_OVERDUE alerts for the affected shipments.

Run as a standalone daemon::

    python -m app.jobs.scheduler

or enable ``SCHEDULER_ENABLED=true`` to run it on a background thread inside the
FastAPI app (see ``app.main.create_app``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import SessionLocal
from app.jobs.service import run_overdue_check

logger = logging.getLogger(__name__)


def run_once(session_factory: sessionmaker = SessionLocal) -> dict:
    """Execute one overdue-alert check against ``session_factory``."""
    with session_factory() as db:
        report = run_overdue_check(db)
    logger.info(
        "Overdue alert check: checked=%s created=%s resolved=%s",
        report["checked"],
        report["created"],
        report["resolved"],
    )
    return report


def run_loop(
    *,
    interval_seconds: int | None = None,
    session_factory: sessionmaker = SessionLocal,
    stop_event: threading.Event | None = None,
    on_tick: Callable[[dict], None] | None = None,
) -> None:
    """Poll forever (until ``stop_event``) running one check per interval.

    ``on_tick`` is an optional hook (logging/tests) invoked with each report.
    """
    stop = stop_event if stop_event is not None else threading.Event()
    interval = interval_seconds or settings.SCHEDULER_INTERVAL_SECONDS
    logger.info("Scheduler started (interval=%ss)", interval)

    # Run once immediately so a restart converges without waiting a full cycle.
    try:
        report = run_once(session_factory)
        if on_tick:
            on_tick(report)
    except Exception:  # noqa: BLE001 - keep the loop alive on transient errors
        logger.exception("Overdue alert check failed at startup")

    while not stop.wait(interval):
        try:
            report = run_once(session_factory)
        except Exception:  # noqa: BLE001
            logger.exception("Overdue alert check failed")
            continue
        if on_tick:
            on_tick(report)

    logger.info("Scheduler stopped")


def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    stop_event = threading.Event()

    # Use a daemon thread to keep ctrl-c clean while the loop blocks the main
    # thread; signals set the stop event so a cycle ends promptly.
    def _handle_signal(_signum, _frame) -> None:  # noqa: ANN001 - signal args
        logger.info("Signal received, shutting down")
        stop_event.set()

    import signal

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    worker = threading.Thread(
        target=run_loop,
        kwargs={"interval_seconds": settings.SCHEDULER_INTERVAL_SECONDS, "stop_event": stop_event},
        daemon=True,
        name="overdue-alert-scheduler",
    )
    worker.start()
    worker.join()


if __name__ == "__main__":
    main()