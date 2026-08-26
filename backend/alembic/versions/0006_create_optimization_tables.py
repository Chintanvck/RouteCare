"""create optimization_requests and optimization_recommendations

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24

Phase 6 (Schedule Optimization Engine). Implements docs/04_Database_Design.md
sections 11-12, extended per app/models/optimization.py's docstring:
`mode`, `target_date`/`search_days`/`new_patient_id`/
`new_appointment_duration_minutes`, `error_message` on the request;
`explanation`, `solver_status` on the recommendation.

`optimization_requests.accepted_recommendation_id` is a plain UUID
column, not a foreign key - see the model docstring for why (avoids a
circular FK between the two tables).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("therapist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("therapists.id"), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "mode",
            postgresql.ENUM("DAY_SCHEDULE_OPTIMIZATION", "NEW_PATIENT_PLACEMENT", name="optimization_mode"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="optimization_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("search_days", sa.Integer(), nullable=True),
        sa.Column("new_patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("new_appointment_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("accepted_recommendation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_optimization_requests_clinic_id", "optimization_requests", ["clinic_id"])
    op.create_index("ix_optimization_requests_therapist_id", "optimization_requests", ["therapist_id"])

    op.create_table(
        "optimization_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "optimization_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("optimization_requests.id"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("efficiency_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("total_drive_minutes", sa.Integer(), nullable=False),
        sa.Column("total_distance_miles", sa.Numeric(7, 2), nullable=False),
        sa.Column("time_saved_minutes", sa.Integer(), nullable=True),
        sa.Column("miles_saved", sa.Numeric(7, 2), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommendation_data", postgresql.JSONB(), nullable=False),
        sa.Column("solver_status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_optimization_recommendations_request_id", "optimization_recommendations", ["optimization_request_id"]
    )


def downgrade() -> None:
    op.drop_table("optimization_recommendations")
    op.drop_table("optimization_requests")
    postgresql.ENUM(name="optimization_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="optimization_mode").drop(op.get_bind(), checkfirst=True)
