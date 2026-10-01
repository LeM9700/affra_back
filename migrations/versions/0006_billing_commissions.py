"""Facturation : customers, customer_invoices, invoice_lines, invoice_sequences, commissions

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

Garde-fous en base (difficile à falsifier silencieusement) :
- factures et lignes immuables (ni UPDATE ni DELETE) ;
- règle de commission vérifiée par CHECK : tranches = montant HT / 100 000 (division entière),
  commission = tranches × 10 000 ;
- montants d'une commission figés ; une commission PAID ne peut plus changer.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COMMISSION_STATUSES = "'DUE', 'PAID', 'NOT_DUE', 'CANCELLED'"
SOURCE_SYSTEMS = "'MANUAL', 'IMPORT', 'WEBHOOK', 'API'"


def _uuid(name: str, *args, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _admin_fk(name: str) -> sa.Column:
    return _uuid(name, sa.ForeignKey("admin_users.id", ondelete="RESTRICT"))


def upgrade() -> None:
    op.create_table(
        "customers",
        _uuid("id", primary_key=True),
        _uuid("lead_id", sa.ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("billing_name", sa.String(200), nullable=False),
        sa.Column("billing_address_line1", sa.String(200), nullable=False),
        sa.Column("billing_address_line2", sa.String(200)),
        sa.Column("billing_postal_code", sa.String(10), nullable=False),
        sa.Column("billing_city", sa.String(100), nullable=False),
        sa.Column("billing_country", sa.String(60), nullable=False, server_default="France"),
        sa.Column("billing_email", sa.String(254)),
        sa.Column("billing_siret", sa.String(14)),
        sa.Column("billing_vat_number", sa.String(20)),
        _admin_fk("created_by"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("lead_id", name="uq_customers_lead_id"),
    )

    op.create_table(
        "invoice_sequences",
        sa.Column("year", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("last_value", sa.Integer, nullable=False),
        sa.CheckConstraint("last_value > 0", name="ck_invoice_sequences_positive"),
    )

    op.create_table(
        "customer_invoices",
        _uuid("id", primary_key=True),
        _uuid("customer_id", sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_number", sa.String(40), nullable=False),
        sa.Column("invoice_date", sa.Date, nullable=False),
        sa.Column("service_date", sa.Date),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("total_ht_cents", sa.BigInteger, nullable=False),
        sa.Column("total_vat_cents", sa.BigInteger, nullable=False),
        sa.Column("total_ttc_cents", sa.BigInteger, nullable=False),
        sa.Column("billing_name", sa.String(200), nullable=False),
        sa.Column("billing_address_line1", sa.String(200), nullable=False),
        sa.Column("billing_address_line2", sa.String(200)),
        sa.Column("billing_postal_code", sa.String(10), nullable=False),
        sa.Column("billing_city", sa.String(100), nullable=False),
        sa.Column("billing_country", sa.String(60), nullable=False),
        sa.Column("billing_email", sa.String(254)),
        sa.Column("billing_siret", sa.String(14)),
        sa.Column("billing_vat_number", sa.String(20)),
        sa.Column("seller_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("payment_terms", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("external_reference", sa.String(100)),
        sa.Column("source_system", sa.String(30), nullable=False, server_default="MANUAL"),
        _admin_fk("created_by"),
        _ts("created_at"),
        sa.UniqueConstraint("invoice_number", name="uq_customer_invoices_invoice_number"),
        sa.CheckConstraint("total_ht_cents > 0", name="ck_customer_invoices_amount_positive"),
        sa.CheckConstraint("total_vat_cents >= 0", name="ck_customer_invoices_vat_non_negative"),
        sa.CheckConstraint("total_ttc_cents = total_ht_cents + total_vat_cents", name="ck_customer_invoices_ttc"),
        sa.CheckConstraint("due_date >= invoice_date", name="ck_customer_invoices_due_date"),
        sa.CheckConstraint("length(trim(invoice_number)) > 0", name="ck_customer_invoices_number_not_blank"),
        sa.CheckConstraint(f"source_system IN ({SOURCE_SYSTEMS})", name="ck_customer_invoices_source_system"),
    )
    op.create_index("ix_customer_invoices_customer_date", "customer_invoices", ["customer_id", "invoice_date"])
    op.create_index("ix_customer_invoices_invoice_date", "customer_invoices", ["invoice_date"])
    # Futur import / webhook : une référence externe ne peut être importée qu'une fois par système.
    op.create_index(
        "uq_customer_invoices_external_reference",
        "customer_invoices",
        ["source_system", "external_reference"],
        unique=True,
        postgresql_where=sa.text("external_reference IS NOT NULL"),
    )

    op.create_table(
        "invoice_lines",
        _uuid("id", primary_key=True),
        _uuid("invoice_id", sa.ForeignKey("customer_invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit", sa.String(20)),
        sa.Column("unit_price_ht_cents", sa.BigInteger, nullable=False),
        sa.Column("vat_rate_bp", sa.Integer, nullable=False),
        sa.Column("total_ht_cents", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("invoice_id", "position", name="uq_invoice_lines_position"),
        sa.CheckConstraint("quantity > 0", name="ck_invoice_lines_quantity"),
        sa.CheckConstraint("unit_price_ht_cents >= 0", name="ck_invoice_lines_unit_price"),
        sa.CheckConstraint("total_ht_cents >= 0", name="ck_invoice_lines_total"),
        sa.CheckConstraint("vat_rate_bp BETWEEN 0 AND 10000", name="ck_invoice_lines_vat_rate"),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    op.create_table(
        "commissions",
        _uuid("id", primary_key=True),
        _uuid("invoice_id", sa.ForeignKey("customer_invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_amount_cents", sa.BigInteger, nullable=False),
        sa.Column("number_of_brackets", sa.Integer, nullable=False),
        sa.Column("commission_amount_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        _uuid("attribution_decision_id", sa.ForeignKey("attribution_decisions.id", ondelete="RESTRICT")),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        _admin_fk("paid_by"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("invoice_id", name="uq_commissions_invoice_id"),
        sa.CheckConstraint("invoice_amount_cents > 0", name="ck_commissions_invoice_amount_positive"),
        sa.CheckConstraint(
            "number_of_brackets = invoice_amount_cents / 100000", name="ck_commissions_brackets_rule"
        ),
        sa.CheckConstraint(
            "commission_amount_cents = number_of_brackets * 10000", name="ck_commissions_amount_rule"
        ),
        sa.CheckConstraint(f"status IN ({COMMISSION_STATUSES})", name="ck_commissions_status"),
        sa.CheckConstraint("(status = 'PAID') = (paid_at IS NOT NULL)", name="ck_commissions_paid_at"),
        sa.CheckConstraint(
            "status <> 'NOT_DUE' OR commission_amount_cents = 0", name="ck_commissions_not_due_zero"
        ),
    )
    op.create_index("ix_commissions_status", "commissions", ["status"])

    # --- Immuabilité
    op.execute(
        """
        CREATE FUNCTION billing_immutable_row() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable (% forbidden): issue a credit note instead', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("customer_invoices", "invoice_lines"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION billing_immutable_row();"
        )

    op.execute(
        """
        CREATE FUNCTION commissions_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'commissions cannot be deleted';
            END IF;
            IF NEW.invoice_id <> OLD.invoice_id
               OR NEW.invoice_amount_cents <> OLD.invoice_amount_cents
               OR NEW.number_of_brackets <> OLD.number_of_brackets
               OR NEW.commission_amount_cents <> OLD.commission_amount_cents
               OR NEW.created_at <> OLD.created_at THEN
                RAISE EXCEPTION 'commission amounts are immutable';
            END IF;
            IF OLD.status = 'PAID' AND (NEW.status <> 'PAID' OR NEW.paid_at IS DISTINCT FROM OLD.paid_at
                                        OR NEW.paid_by IS DISTINCT FROM OLD.paid_by) THEN
                RAISE EXCEPTION 'a paid commission cannot be modified';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_commissions_guard BEFORE UPDATE OR DELETE ON commissions "
        "FOR EACH ROW EXECUTE FUNCTION commissions_guard();"
    )


def downgrade() -> None:
    op.drop_table("commissions")
    op.execute("DROP FUNCTION IF EXISTS commissions_guard()")
    op.drop_table("invoice_lines")
    op.drop_table("customer_invoices")
    op.execute("DROP FUNCTION IF EXISTS billing_immutable_row()")
    op.drop_table("invoice_sequences")
    op.drop_table("customers")
