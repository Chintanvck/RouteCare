"""create import tables (imports, import_rows, import_errors)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-22

Implements docs/04_Database_Design.md sections 13 ("imports") and 14
("import_errors"), extended with import_rows (not in the doc, but
necessary - see backend/app/models/import_row.py docstring) and a few
extra columns on `imports` needed for the multi-step wizard to persist
state between separate HTTP requests (stored_file_path,
detected_headers, column_mapping, processed_records).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("stored_file_path", sa.String(length=500), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False, server_default="theraoffice"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "PROCESSING",
                "COMPLETED",
                "COMPLETED_WITH_ERRORS",
                "FAILED",
                name="import_status",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("detected_headers", postgresql.JSONB(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(), nullable=True),
        sa.Column("total_records", sa.Integer(), nullable=True),
        sa.Column("processed_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_records", sa.Integer(), nullable=True),
        sa.Column("invalid_records", sa.Integer(), nullable=True),
        sa.Column("duplicate_records", sa.Integer(), nullable=True),
        sa.Column("new_records", sa.Integer(), nullable=True),
        sa.Column("successful_records", sa.Integer(), nullable=True),
        sa.Column("failed_records", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_imports_clinic_id", "imports", ["clinic_id"])

    op.create_table(
        "import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imports.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("mapped_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "classification",
            postgresql.ENUM(
                "VALID", "INVALID", "DUPLICATE_EXACT", "DUPLICATE_PROBABLE", name="import_row_classification"
            ),
            nullable=False,
        ),
        sa.Column("errors", postgresql.JSONB(), nullable=True),
        sa.Column("duplicate_patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("duplicate_of_row_number", sa.Integer(), nullable=True),
        sa.Column("duplicate_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("imported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=True),
    )
    op.create_index("ix_import_rows_import_id", "import_rows", ["import_id"])

    op.create_table(
        "import_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imports.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_import_errors_import_id", "import_errors", ["import_id"])


def downgrade() -> None:
    op.drop_table("import_errors")
    op.drop_table("import_rows")
    op.drop_table("imports")
    postgresql.ENUM(name="import_row_classification").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="import_status").drop(op.get_bind(), checkfirst=True)
