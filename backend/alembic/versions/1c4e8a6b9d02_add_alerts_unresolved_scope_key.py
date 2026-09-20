"""add alerts unresolved scope key (concurrency-safe active_key)

Revision ID: 1c4e8a6b9d02
Revises: 8a3965225cfe
Create Date: 2026-09-20 12:00:00.000000

The ``alerts.active_key`` column is NON-NULL only while an alert is unresolved
(``"<type>:<entity_type>:<entity_id>"``); resolved alerts set it to NULL. A
UNIQUE constraint on it guarantees, at the InnoDB level, that two concurrent
requests can never both open the same alert. MySQL treats NULLs as distinct, so
any number of resolved history rows is allowed.

Existing open alerts are backfilled from their columns, and any duplicate open
alerts left behind by the pre-fix check-then-insert race are collapsed (all but
the earliest per scope are resolved) before the unique constraint is added.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c4e8a6b9d02"
down_revision: Union[str, None] = "8a3965225cfe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("active_key", sa.String(length=130), nullable=True),
    )
    # Backfill a deterministic key for every currently-open alert.
    op.execute(
        "UPDATE alerts "
        "SET active_key = CONCAT(type, ':', entity_type, ':', entity_id) "
        "WHERE is_resolved = 0"
    )
    # Collapse legacy duplicate open episodes: keep the earliest row per scope,
    # resolve the rest (their active_key reverts to NULL).
    op.execute(
        "UPDATE alerts a "
        "JOIN ("
        "    SELECT active_key, MIN(id) AS keep_id "
        "    FROM alerts "
        "    WHERE active_key IS NOT NULL "
        "    GROUP BY active_key "
        "    HAVING COUNT(*) > 1 "
        ") dups ON a.active_key = dups.active_key AND a.id <> dups.keep_id "
        "SET a.is_resolved = 1, a.resolved_at = NOW(6), a.active_key = NULL"
    )
    op.create_unique_constraint(
        op.f("uq_alerts_active_key"), "alerts", ["active_key"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_alerts_active_key"), "alerts", type_="unique")
    op.drop_column("alerts", "active_key")