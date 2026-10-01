"""upgrade / downgrade sur une base contenant déjà des devis (base dédiée affra_migr_test)."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.conftest import TEST_DATABASE_URL, run_alembic

MIGR_DATABASE_URL = os.environ.get(
    "TEST_MIGRATIONS_DATABASE_URL", TEST_DATABASE_URL.rsplit("/", 1)[0] + "/affra_migr_test"
)


@pytest.fixture
async def migr_engine():
    engine = create_async_engine(MIGR_DATABASE_URL, poolclass=NullPool, connect_args={"ssl": False})
    yield engine
    await engine.dispose()


async def _scalar(engine, sql: str):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


async def test_upgrade_downgrade_with_existing_devis(migr_engine):
    run_alembic("downgrade", "base", database_url=MIGR_DATABASE_URL)
    run_alembic("upgrade", "0004", database_url=MIGR_DATABASE_URL)

    async with migr_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO devis (id, created_at, prenom, email, telephone, ville, statut) VALUES "
                "(gen_random_uuid(), now() - interval '10 days', 'Ana', 'ana@example.com', '0601', 'Alès', 'nouveau'),"
                "(gen_random_uuid(), now() - interval '2 days', 'Ana', 'ANA@example.com', NULL, 'Nîmes', 'accepte'),"
                "(gen_random_uuid(), now(), 'Léo', 'leo@example.com', '0602', 'Uzès', 'nouveau'),"
                "(gen_random_uuid(), now(), NULL, 'inconnu@migrated.local', NULL, NULL, 'archive')"
            )
        )

    run_alembic("upgrade", "head", database_url=MIGR_DATABASE_URL)
    assert await _scalar(migr_engine, "SELECT count(*) FROM leads") == 2
    assert await _scalar(migr_engine, "SELECT count(*) FROM devis WHERE lead_id IS NOT NULL") == 3
    assert await _scalar(migr_engine, "SELECT count(*) FROM attribution_decisions") == 2
    assert await _scalar(migr_engine, "SELECT count(*) FROM leads WHERE current_decision_id IS NULL") == 0
    assert await _scalar(migr_engine, "SELECT ville FROM leads WHERE lower(email) = 'ana@example.com'") == "Nîmes"
    assert await _scalar(migr_engine, "SELECT telephone FROM leads WHERE lower(email) = 'ana@example.com'") == "0601"
    assert await _scalar(
        migr_engine, "SELECT count(*) FROM leads WHERE financial_attribution = 'DISPUTED' AND marketing_source = 'UNKNOWN'"
    ) == 2

    run_alembic("downgrade", "0004", database_url=MIGR_DATABASE_URL)
    assert await _scalar(migr_engine, "SELECT count(*) FROM devis") == 4
    assert await _scalar(migr_engine, "SELECT to_regclass('public.leads') IS NULL") is True
    assert await _scalar(
        migr_engine, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'devis' AND column_name = 'lead_id'"
    ) == 0

    run_alembic("upgrade", "head", database_url=MIGR_DATABASE_URL)
    assert await _scalar(migr_engine, "SELECT count(*) FROM leads") == 2
    run_alembic("downgrade", "base", database_url=MIGR_DATABASE_URL)
