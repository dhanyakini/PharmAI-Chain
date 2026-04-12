"""Add agent_shipment_memory and agent_decision_logs for agentic reroute observability.

Revision ID: 20260412_0001
Revises:
Create Date: 2026-04-12

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260412_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "agent_shipment_memory" not in tables:
        op.create_table(
            "agent_shipment_memory",
            sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("memory_json", sa.JSON(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )

    if "agent_decision_logs" not in tables:
        op.create_table(
            "agent_decision_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, primary_key=True),
            sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("decision_json", sa.JSON(), nullable=False),
            sa.Column("planner_json", sa.JSON(), nullable=True),
            sa.Column("critic_json", sa.JSON(), nullable=True),
            sa.Column("tool_traces_json", sa.JSON(), nullable=True),
            sa.Column("supervisor_json", sa.JSON(), nullable=True),
            sa.Column("operator_feedback", sa.String(length=32), nullable=True),
        )
        op.create_index("ix_agent_decision_logs_shipment_id", "agent_decision_logs", ["shipment_id"])
        op.create_index(
            "ix_agent_decision_shipment_ts",
            "agent_decision_logs",
            ["shipment_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "agent_decision_logs" in tables:
        op.drop_index("ix_agent_decision_shipment_ts", table_name="agent_decision_logs")
        op.drop_index("ix_agent_decision_logs_shipment_id", table_name="agent_decision_logs")
        op.drop_table("agent_decision_logs")
    if "agent_shipment_memory" in tables:
        op.drop_table("agent_shipment_memory")
