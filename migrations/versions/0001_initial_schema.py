"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "devis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("type_client", sa.String(50)),
        sa.Column("type_projet", sa.String(50)),
        sa.Column("nb_bornes", sa.String(20)),
        sa.Column("puissance", sa.String(20)),
        sa.Column("tableau_normes", sa.String(20)),
        sa.Column("description", sa.Text),
        sa.Column("ville", sa.String(100)),
        sa.Column("code_postal", sa.String(10)),
        sa.Column("delai", sa.String(30)),
        sa.Column("prenom", sa.String(100)),
        sa.Column("nom", sa.String(100)),
        sa.Column("email", sa.String(254)),
        sa.Column("telephone", sa.String(20)),
        sa.Column("statut", sa.String(30), nullable=False, server_default="nouveau"),
        sa.Column("rgpd_consent_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "blog_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(200), unique=True, nullable=False),
        sa.Column("titre", sa.String(300), nullable=False),
        sa.Column("contenu_markdown", sa.Text),
        sa.Column("meta_description", sa.String(160)),
        sa.Column("og_image_url", sa.String(500)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("published", sa.Boolean, nullable=False, server_default="false"),
    )

    op.create_table(
        "portfolio_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(200), unique=True, nullable=False),
        sa.Column("titre", sa.String(300), nullable=False),
        sa.Column("type_client", sa.String(50)),
        sa.Column("type_borne", sa.String(100)),
        sa.Column("puissance_kw", sa.Numeric(6, 1)),
        sa.Column("ville", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("image_urls", postgresql.ARRAY(sa.String)),
        sa.Column("subvention_obtenue", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published", sa.Boolean, nullable=False, server_default="false"),
    )

    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ville", sa.String(100), nullable=False),
        sa.Column("departement", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
    )

    # Indexes
    op.create_index("ix_blog_posts_slug", "blog_posts", ["slug"])
    op.create_index("ix_blog_posts_published", "blog_posts", ["published", "published_at"])
    op.create_index("ix_portfolio_items_published", "portfolio_items", ["published", "created_at"])
    op.create_index("ix_zones_active", "zones", ["active", "departement"])
    op.create_index("ix_devis_created_at", "devis", ["created_at"])


def downgrade() -> None:
    op.drop_table("zones")
    op.drop_table("portfolio_items")
    op.drop_table("blog_posts")
    op.drop_table("devis")
