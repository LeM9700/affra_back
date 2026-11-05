"""Zones : slug de liaison avec les pages ville du front

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05

Le front reliait chaque zone à sa page /zone-intervention/{slug} par le NOM affiché : une faute
d'accent dans la saisie suffisait à casser le lien sans erreur. Le slug devient la clé de liaison.
Remplissage des lignes existantes depuis `ville` (même règle que le front), doublons suffixés.
"""
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def slugify(value: str) -> str:
    """Copie figée de app.services.slug.slugify : une migration ne doit pas suivre le code applicatif."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def upgrade() -> None:
    op.add_column("zones", sa.Column("slug", sa.String(120), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, ville FROM zones ORDER BY departement, ville, id")).all()
    used: set[str] = set()
    for zone_id, ville in rows:
        base = slugify(ville) or "zone"
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        conn.execute(sa.text("UPDATE zones SET slug = :slug WHERE id = :id"), {"slug": slug, "id": zone_id})

    op.alter_column("zones", "slug", nullable=False)
    op.create_unique_constraint("uq_zones_slug", "zones", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_zones_slug", "zones", type_="unique")
    op.drop_column("zones", "slug")
