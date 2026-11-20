"""Import de factures : pièces justificatives, remise par ligne, références du logiciel d'origine

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-02

- invoice_documents : fichier importé (empreinte SHA-256 unique, clé de stockage R2), données lues,
  contrôles, statut de revue, facture créée après validation humaine ;
- invoice_lines.discount_bp (remise de ligne, 0 par défaut : aucune facture existante ne change) et
  description portée à 2 000 caractères (descriptifs détaillés des forfaits) ;
- customer_invoices.external_customer_ref / external_quote_ref (CLT… / DEV… du logiciel d'origine).

Les ajouts de colonnes (avec valeur par défaut) ne réécrivent aucune ligne : les triggers
d'immuabilité des factures ne sont pas déclenchés.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

STATUSES = "'PENDING_REVIEW', 'CONFIRMED', 'REJECTED'"
METHODS = "'PDF_TEXT', 'AI', 'NONE'"
CONTENT_TYPES = "'application/pdf', 'image/jpeg', 'image/png'"


def upgrade() -> None:
    op.add_column("invoice_lines", sa.Column("discount_bp", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_invoice_lines_discount", "invoice_lines", "discount_bp BETWEEN 0 AND 10000")
    op.alter_column(
        "invoice_lines", "description", type_=sa.String(2000), existing_type=sa.String(500), existing_nullable=False
    )

    op.add_column("customer_invoices", sa.Column("external_customer_ref", sa.String(40)))
    op.add_column("customer_invoices", sa.Column("external_quote_ref", sa.String(40)))

    op.create_table(
        "invoice_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_invoices.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("storage_key", sa.String(300), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("extraction_method", sa.String(20), nullable=False),
        sa.Column("extraction", postgresql.JSONB(), nullable=False),
        sa.Column("analysis", postgresql.JSONB(), nullable=False),
        sa.Column("confirmation", postgresql.JSONB()),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_invoice_documents_status"),
        sa.CheckConstraint(f"extraction_method IN ({METHODS})", name="ck_invoice_documents_method"),
        sa.CheckConstraint(f"content_type IN ({CONTENT_TYPES})", name="ck_invoice_documents_content_type"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_invoice_documents_sha256"),
        sa.CheckConstraint("size_bytes > 0", name="ck_invoice_documents_size"),
        # Une pièce confirmée est liée à sa facture ; une pièce rejetée a un motif.
        sa.CheckConstraint("(status = 'CONFIRMED') = (invoice_id IS NOT NULL)", name="ck_invoice_documents_confirmed"),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR length(trim(coalesce(rejection_reason, ''))) > 0",
            name="ck_invoice_documents_rejected_reason",
        ),
    )
    op.create_index("ix_invoice_documents_lead_created", "invoice_documents", ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_invoice_documents_lead_created", table_name="invoice_documents")
    op.drop_table("invoice_documents")
    op.drop_column("customer_invoices", "external_quote_ref")
    op.drop_column("customer_invoices", "external_customer_ref")
    op.drop_constraint("ck_invoice_lines_discount", "invoice_lines", type_="check")
    op.drop_column("invoice_lines", "discount_bp")
    # Les descriptifs de plus de 500 caractères sont tronqués (ALTER TYPE … USING : réécriture DDL,
    # qui ne déclenche pas les triggers d'immuabilité ligne à ligne).
    op.alter_column(
        "invoice_lines",
        "description",
        type_=sa.String(500),
        existing_type=sa.String(2000),
        postgresql_using="left(description, 500)",
    )
