"""Refonte devis IRVE — nouveaux champs questionnaire lead-gen

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Supprimer les anciens champs obsolètes
    op.drop_column("devis", "type_projet")
    op.drop_column("devis", "nb_bornes")
    op.drop_column("devis", "puissance")
    op.drop_column("devis", "tableau_normes")
    op.drop_column("devis", "description")
    op.drop_column("devis", "code_postal")
    op.drop_column("devis", "nom")

    # Ajouter les nouveaux champs questionnaire IRVE
    op.add_column("devis", sa.Column("possede_vehicule", sa.String(50), nullable=True))
    op.add_column("devis", sa.Column("distance_quotidienne", sa.String(30), nullable=True))
    op.add_column("devis", sa.Column("distance_tableau", sa.String(30), nullable=True))

    # Mettre à jour les valeurs de type_client (le type reste VARCHAR, pas d'enum SQL)
    # Les nouvelles valeurs sont : maison | copropriete | entreprise
    # Les anciennes (particulier, pro, promoteur) deviennent NULL pour les anciennes lignes
    op.execute(
        "UPDATE devis SET type_client = NULL "
        "WHERE type_client NOT IN ('maison', 'copropriete', 'entreprise')"
    )

    # Mettre à jour les valeurs de delai
    # Nouvelles valeurs : rapidement | un_deux_mois | pas_urgent
    op.execute(
        "UPDATE devis SET delai = NULL "
        "WHERE delai NOT IN ('rapidement', 'un_deux_mois', 'pas_urgent')"
    )

    # Rendre email NOT NULL (mettre une valeur par défaut pour les lignes existantes sans email)
    op.execute("UPDATE devis SET email = 'inconnu@migrated.local' WHERE email IS NULL")
    op.alter_column("devis", "email", nullable=False, existing_type=sa.String(254))


def downgrade() -> None:
    # Remettre email nullable
    op.alter_column("devis", "email", nullable=True, existing_type=sa.String(254))

    # Supprimer les nouveaux champs
    op.drop_column("devis", "possede_vehicule")
    op.drop_column("devis", "distance_quotidienne")
    op.drop_column("devis", "distance_tableau")

    # Remettre les anciens champs (nullable)
    op.add_column("devis", sa.Column("type_projet", sa.String(50), nullable=True))
    op.add_column("devis", sa.Column("nb_bornes", sa.String(20), nullable=True))
    op.add_column("devis", sa.Column("puissance", sa.String(20), nullable=True))
    op.add_column("devis", sa.Column("tableau_normes", sa.String(20), nullable=True))
    op.add_column("devis", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("devis", sa.Column("code_postal", sa.String(10), nullable=True))
    op.add_column("devis", sa.Column("nom", sa.String(100), nullable=True))
