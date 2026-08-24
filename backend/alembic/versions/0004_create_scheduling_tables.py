"""create scheduling tables (therapists, therapist_availability, patient_availability, appointments)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23

Implements docs/04_Database_Design.md sections 5 (therapists), 6
(therapist_availability), 8 (patient_availability), and 9 (appointments).
Indexes on appointments (clinic_id, therapist_id+scheduled_date,
patient_id+scheduled_date) per section 18's indexing strategy.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "therapists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("license_type", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("home_address", sa.Text(), nullable=True),
        sa.Column("home_latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("home_longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("max_daily_hours", sa.Integer(), nullable=True),
        sa.Column("max_drive_time_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_therapists_clinic_id", "therapists", ["clinic_id"])

    op.create_table(
        "therapist_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("therapist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("therapists.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_therapist_availability_therapist_id", "therapist_availability", ["therapist_id"])

    op.create_table(
        "patient_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "preference_type",
            postgresql.ENUM("PREFERRED", "AVAILABLE", "NOT_AVAILABLE", name="patient_availability_preference"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_patient_availability_patient_id", "patient_availability", ["patient_id"])

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("therapist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("therapists.id"), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW", name="appointment_status"),
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column(
            "appointment_source",
            postgresql.ENUM("MANUAL", "AI_RECOMMENDED", name="appointment_source"),
            nullable=False,
            server_default="MANUAL",
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_appointments_clinic_id", "appointments", ["clinic_id"])
    op.create_index("ix_appointments_therapist_id_scheduled_date", "appointments", ["therapist_id", "scheduled_date"])
    op.create_index("ix_appointments_patient_id_scheduled_date", "appointments", ["patient_id", "scheduled_date"])


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_table("patient_availability")
    op.drop_table("therapist_availability")
    op.drop_table("therapists")
    postgresql.ENUM(name="appointment_source").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="appointment_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="patient_availability_preference").drop(op.get_bind(), checkfirst=True)
