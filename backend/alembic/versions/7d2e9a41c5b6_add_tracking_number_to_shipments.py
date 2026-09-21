"""add public tracking_number to shipments

Revision ID: 7d2e9a41c5b6
Revises: 60265f5dc3cb
Create Date: 2026-09-21

Adds the public, randomly generated ``tracking_number`` used by the
unauthenticated tracking endpoint. Existing rows are backfilled with unique
random values so the column can be tightened to NOT NULL.
"""

from __future__ import annotations

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7d2e9a41c5b6'
down_revision: Union[str, None] = '60265f5dc3cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _generate_tracking_number(seen: set[str]) -> str:
    while True:
        candidate = f"TRK-{secrets.token_hex(4).upper()}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate


def upgrade() -> None:
    op.add_column('shipments', sa.Column('tracking_number', sa.String(length=32), nullable=True))

    # Backfill existing rows with unique random tracking numbers.
    conn = op.get_bind()
    existing = {
        row[0]
        for row in conn.execute(sa.text("SELECT tracking_number FROM shipments"))
        if row[0]
    }
    ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM shipments"))]
    for shipment_id in ids:
        tracking_number = _generate_tracking_number(existing)
        conn.execute(
            sa.text("UPDATE shipments SET tracking_number = :tn WHERE id = :sid"),
            {"tn": tracking_number, "sid": shipment_id},
        )

    op.alter_column(
        'shipments', 'tracking_number',
        existing_type=sa.String(length=32), nullable=False,
    )
    op.create_index(
        op.f('ix_shipments_tracking_number'), 'shipments', ['tracking_number'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_shipments_tracking_number'), table_name='shipments')
    op.drop_column('shipments', 'tracking_number')
