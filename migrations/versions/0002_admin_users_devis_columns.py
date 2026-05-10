"""Add admin_users table and devis internal columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), unique=True, nullable=False),
        sa.Column("hashed_pw", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.add_column("devis", sa.Column("notes", sa.Text, nullable=True))
    op.add_column("devis", sa.Column("subvention_type", sa.String(30), nullable=True))
    op.add_column("devis", sa.Column("subvention_statut", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("devis", "subvention_statut")
    op.drop_column("devis", "subvention_type")
    op.drop_column("devis", "notes")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
