"""Attribution : visitors, attribution_events, leads, attribution_decisions, devis.lead_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

Compatible base existante : chaque email distinct de `devis` devient un lead historique
(source UNKNOWN, attribution DISPUTED « à arbitrer ») avec une décision initiale journalisée.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SOURCES = (
    "'GOOGLE_ORGANIC', 'GOOGLE_BUSINESS', 'GOOGLE_ADS', 'BING_ORGANIC', 'CHATGPT', 'CLAUDE', "
    "'PERPLEXITY', 'GEMINI', 'REFERRAL', 'DIRECT', 'UNKNOWN'"
)
EVENT_TYPES = "'LANDING', 'QUOTE_STARTED', 'QUOTE_SUBMITTED', 'PHONE_CLICK', 'EMAIL_CLICK', 'WHATSAPP_CLICK', 'PHONE_CALL'"
FINANCIAL = "'AFFRA_DIGITAL', 'NON_AFFRA', 'DISPUTED'"
CONFIDENCE = "'VERIFIED', 'SUPPORTED', 'DECLARED', 'UNKNOWN'"
CHANNELS = "'FORM', 'PHONE', 'EMAIL', 'OTHER'"
LEAD_STATUSES = "'nouveau', 'en_cours', 'client', 'perdu'"


def _uuid(name: str, *args, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kwargs)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "visitors",
        _uuid("id", primary_key=True),
        _uuid("anonymous_id", nullable=False),
        _ts("first_seen_at"),
        _ts("last_seen_at"),
        sa.Column("first_source", sa.String(30)),
        sa.Column("first_medium", sa.String(100)),
        sa.Column("first_campaign", sa.String(150)),
        sa.Column("first_referrer", sa.String(500)),
        sa.Column("first_landing_page", sa.String(500)),
        sa.Column("last_source", sa.String(30)),
        sa.Column("last_medium", sa.String(100)),
        sa.Column("last_campaign", sa.String(150)),
        sa.Column("last_referrer", sa.String(500)),
        sa.Column("last_landing_page", sa.String(500)),
        sa.Column("gclid", sa.String(255)),
        sa.Column("gbraid", sa.String(255)),
        sa.Column("wbraid", sa.String(255)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("anonymous_id", name="uq_visitors_anonymous_id"),
        sa.CheckConstraint(f"first_source IS NULL OR first_source IN ({SOURCES})", name="ck_visitors_first_source"),
        sa.CheckConstraint(f"last_source IS NULL OR last_source IN ({SOURCES})", name="ck_visitors_last_source"),
    )
    op.create_index("ix_visitors_last_seen_at", "visitors", ["last_seen_at"])

    op.create_table(
        "leads",
        _uuid("id", primary_key=True),
        _uuid("visitor_id", sa.ForeignKey("visitors.id", ondelete="SET NULL")),
        sa.Column("prenom", sa.String(100)),
        sa.Column("nom", sa.String(100)),
        sa.Column("email", sa.String(254)),
        sa.Column("telephone", sa.String(20)),
        sa.Column("ville", sa.String(100)),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("marketing_source", sa.String(30), nullable=False),
        sa.Column("marketing_medium", sa.String(100)),
        sa.Column("marketing_campaign", sa.String(150)),
        sa.Column("financial_attribution", sa.String(20), nullable=False),
        sa.Column("attribution_confidence", sa.String(20), nullable=False),
        _uuid("current_decision_id"),
        sa.Column("status", sa.String(20), nullable=False, server_default="nouveau"),
        sa.Column("notes", sa.Text),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(f"channel IN ({CHANNELS})", name="ck_leads_channel"),
        sa.CheckConstraint(f"marketing_source IN ({SOURCES})", name="ck_leads_marketing_source"),
        sa.CheckConstraint(f"financial_attribution IN ({FINANCIAL})", name="ck_leads_financial_attribution"),
        sa.CheckConstraint(f"attribution_confidence IN ({CONFIDENCE})", name="ck_leads_attribution_confidence"),
        sa.CheckConstraint(f"status IN ({LEAD_STATUSES})", name="ck_leads_status"),
    )
    op.create_index("ix_leads_visitor_id", "leads", ["visitor_id"])
    op.create_index("ix_leads_created_at", "leads", ["created_at"])
    op.create_index("ix_leads_financial_attribution", "leads", ["financial_attribution"])
    op.create_index("ix_leads_email_lower", "leads", [sa.text("lower(email)")])

    op.create_table(
        "attribution_decisions",
        _uuid("id", primary_key=True),
        _uuid("lead_id", sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("previous_decision", sa.String(20)),
        sa.Column("previous_confidence", sa.String(20)),
        sa.Column("reason", sa.Text, nullable=False),
        _uuid("created_by", sa.ForeignKey("admin_users.id", ondelete="RESTRICT")),
        _ts("created_at"),
        sa.CheckConstraint(f"decision IN ({FINANCIAL})", name="ck_attribution_decisions_decision"),
        sa.CheckConstraint(f"confidence IN ({CONFIDENCE})", name="ck_attribution_decisions_confidence"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_attribution_decisions_reason"),
    )
    op.create_index("ix_attribution_decisions_lead_created", "attribution_decisions", ["lead_id", "created_at"])
    op.create_foreign_key(
        "fk_leads_current_decision_id", "leads", "attribution_decisions", ["current_decision_id"], ["id"], ondelete="SET NULL"
    )

    # Journal append-only : aucune décision ne peut être réécrite après coup.
    op.execute(
        """
        CREATE FUNCTION attribution_decisions_no_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'attribution_decisions is append-only: record a new decision instead';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_attribution_decisions_no_update BEFORE UPDATE ON attribution_decisions "
        "FOR EACH ROW EXECUTE FUNCTION attribution_decisions_no_update();"
    )

    op.create_table(
        "attribution_events",
        _uuid("id", primary_key=True),
        _uuid("client_event_id"),
        _uuid("visitor_id", sa.ForeignKey("visitors.id", ondelete="CASCADE")),
        _uuid("lead_id", sa.ForeignKey("leads.id", ondelete="SET NULL")),
        _uuid("devis_id", sa.ForeignKey("devis.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("medium", sa.String(100)),
        sa.Column("campaign", sa.String(150)),
        sa.Column("referrer", sa.String(500)),
        sa.Column("landing_page", sa.String(500)),
        sa.Column("page_path", sa.String(500)),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _ts("created_at"),
        sa.UniqueConstraint("client_event_id", name="uq_attribution_events_client_event_id"),
        sa.CheckConstraint(f"event_type IN ({EVENT_TYPES})", name="ck_attribution_events_event_type"),
        sa.CheckConstraint(f"source IN ({SOURCES})", name="ck_attribution_events_source"),
        sa.CheckConstraint("jsonb_typeof(metadata) = 'object'", name="ck_attribution_events_metadata_object"),
        sa.CheckConstraint("pg_column_size(metadata) <= 2048", name="ck_attribution_events_metadata_size"),
    )
    op.create_index("ix_attribution_events_visitor_created", "attribution_events", ["visitor_id", "created_at"])
    op.create_index("ix_attribution_events_type_created", "attribution_events", ["event_type", "created_at"])
    op.create_index("ix_attribution_events_lead_id", "attribution_events", ["lead_id"])

    op.add_column("devis", _uuid("lead_id", nullable=True))
    op.create_foreign_key("fk_devis_lead_id", "devis", "leads", ["lead_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_devis_lead_id", "devis", ["lead_id"])

    # --- Backfill : un lead historique par email distinct (hors placeholder de la migration 0003)
    op.execute(
        """
        INSERT INTO leads (id, prenom, email, telephone, ville, channel, marketing_source,
                           financial_attribution, attribution_confidence, status, created_at, updated_at)
        SELECT gen_random_uuid(),
               (array_agg(prenom ORDER BY created_at DESC) FILTER (WHERE prenom IS NOT NULL))[1],
               (array_agg(email ORDER BY created_at DESC))[1],
               (array_agg(telephone ORDER BY created_at DESC) FILTER (WHERE telephone IS NOT NULL))[1],
               (array_agg(ville ORDER BY created_at DESC) FILTER (WHERE ville IS NOT NULL))[1],
               'FORM', 'UNKNOWN', 'DISPUTED', 'UNKNOWN', 'nouveau', min(created_at), now()
        FROM devis
        WHERE email IS NOT NULL AND email <> 'inconnu@migrated.local'
        GROUP BY lower(email)
        """
    )
    op.execute(
        "UPDATE devis d SET lead_id = l.id FROM leads l "
        "WHERE d.lead_id IS NULL AND lower(d.email) = lower(l.email)"
    )
    op.execute(
        """
        INSERT INTO attribution_decisions (id, lead_id, decision, confidence, reason, created_at)
        SELECT gen_random_uuid(), id, 'DISPUTED', 'UNKNOWN',
               'Migration 0005 : lead historique antérieur au tracking d''attribution. Arbitrage manuel requis.',
               now()
        FROM leads
        """
    )
    op.execute("UPDATE leads l SET current_decision_id = d.id FROM attribution_decisions d WHERE d.lead_id = l.id")


def downgrade() -> None:
    op.drop_index("ix_devis_lead_id", table_name="devis")
    op.drop_constraint("fk_devis_lead_id", "devis", type_="foreignkey")
    op.drop_column("devis", "lead_id")

    op.drop_table("attribution_events")

    op.drop_constraint("fk_leads_current_decision_id", "leads", type_="foreignkey")
    op.execute("DROP TRIGGER IF EXISTS trg_attribution_decisions_no_update ON attribution_decisions")
    op.execute("DROP FUNCTION IF EXISTS attribution_decisions_no_update()")
    op.drop_table("attribution_decisions")
    op.drop_table("leads")
    op.drop_table("visitors")
