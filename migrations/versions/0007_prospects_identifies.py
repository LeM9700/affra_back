"""Prospects identifiés et suivi des pages : PAGE_VIEW, CALLBACK_REQUESTED, identité visiteur

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30

- deux nouveaux types d'événements (pages vues, demande de rappel) ;
- identité facultative du visiteur (nom, téléphone E.164, date du consentement) ;
- index pour la liste des prospects (activité récente par visiteur) et la recherche par téléphone.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

OLD_EVENT_TYPES = (
    "'LANDING', 'QUOTE_STARTED', 'QUOTE_SUBMITTED', 'PHONE_CLICK', 'EMAIL_CLICK', 'WHATSAPP_CLICK', 'PHONE_CALL'"
)
NEW_EVENT_TYPES = OLD_EVENT_TYPES + ", 'PAGE_VIEW', 'CALLBACK_REQUESTED'"


def _replace_event_check(values: str) -> None:
    op.drop_constraint("ck_attribution_events_event_type", "attribution_events", type_="check")
    op.create_check_constraint("ck_attribution_events_event_type", "attribution_events", f"event_type IN ({values})")


def upgrade() -> None:
    _replace_event_check(NEW_EVENT_TYPES)

    op.add_column("visitors", sa.Column("contact_name", sa.String(100)))
    op.add_column("visitors", sa.Column("contact_phone", sa.String(20)))
    op.add_column("visitors", sa.Column("contact_consent_at", sa.DateTime(timezone=True)))
    op.add_column("visitors", sa.Column("identified_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_visitors_contact_phone_e164",
        "visitors",
        r"contact_phone IS NULL OR contact_phone ~ '^\+33[1-79][0-9]{8}$'",
    )
    # Pas d'identité sans consentement enregistré.
    op.create_check_constraint(
        "ck_visitors_contact_consent",
        "visitors",
        "(contact_phone IS NULL AND contact_name IS NULL) OR contact_consent_at IS NOT NULL",
    )
    # Liste des prospects : agrégat des événements récents (pages vues comprises, volume x5).
    op.create_index("ix_attribution_events_created_at", "attribution_events", ["created_at"])
    op.create_index(
        "ix_visitors_contact_phone",
        "visitors",
        ["contact_phone"],
        postgresql_where=sa.text("contact_phone IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM attribution_events WHERE event_type IN ('PAGE_VIEW', 'CALLBACK_REQUESTED')")
    _replace_event_check(OLD_EVENT_TYPES)
    op.drop_index("ix_attribution_events_created_at", table_name="attribution_events")
    op.drop_index("ix_visitors_contact_phone", table_name="visitors")
    op.drop_constraint("ck_visitors_contact_consent", "visitors", type_="check")
    op.drop_constraint("ck_visitors_contact_phone_e164", "visitors", type_="check")
    for column in ("identified_at", "contact_consent_at", "contact_phone", "contact_name"):
        op.drop_column("visitors", column)
