"""Add testimonials module for SEO-ready social proof

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "testimonials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("initiales", sa.String(length=10), nullable=False),
        sa.Column("ville", sa.String(length=100), nullable=False),
        sa.Column("departement", sa.String(length=3), nullable=False),
        sa.Column("type_client", sa.String(length=30), nullable=False),
        sa.Column("type_projet", sa.String(length=120), nullable=True),
        sa.Column("resultat", sa.String(length=160), nullable=True),
        sa.Column("temoignage", sa.Text(), nullable=False),
        sa.Column("source_channel", sa.String(length=30), nullable=False, server_default="formulaire_web"),
        sa.Column("consent_publication", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_testimonials_status", "testimonials", ["status"])
    op.create_index("ix_testimonials_published_at", "testimonials", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_testimonials_published_at", table_name="testimonials")
    op.drop_index("ix_testimonials_status", table_name="testimonials")
    op.drop_table("testimonials")
