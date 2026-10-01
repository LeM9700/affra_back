"""Fixtures de test.

Les tests tournent sur une base PostgreSQL LOCALE dédiée (JSONB, ON CONFLICT, triggers, CHECK).
TEST_DATABASE_URL (défaut : postgresql+asyncpg://postgres@127.0.0.1:55432/affra_test).

Garde-fou : refus de démarrer si l'hôte n'est pas local ou si le nom de base ne contient pas "test".
Les variables d'environnement posées ici priment sur backend/.env (qui peut pointer vers Railway).
"""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/affra_test"
)


def _assert_safe_database(url: str) -> None:
    parts = urlsplit(url.replace("+asyncpg", ""))
    if parts.hostname not in ("127.0.0.1", "localhost") or "test" not in parts.path.rsplit("/", 1)[-1]:
        raise RuntimeError(f"Refusing to run tests against non-local / non-test database: {parts.hostname}{parts.path}")


_assert_safe_database(TEST_DATABASE_URL)
os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "API_SECRET_KEY": "test-api-key",
        "REVALIDATION_SECRET": "test-revalidation-secret",
        "ENVIRONMENT": "test",
        "RESEND_API_KEY": "",
        "OPERATOR_EMAIL": "",
        "GOOGLE_SERVICE_ACCOUNT_JSON": "",
        "GOOGLE_SHEETS_SPREADSHEET_ID": "",
        "NEXTJS_REVALIDATE_URL": "",
    }
)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app import database  # noqa: E402

# NullPool : aucune connexion réutilisée entre boucles d'événements de tests différents.
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, connect_args={"ssl": False})
database.AsyncSessionLocal.configure(bind=test_engine)

from app.main import app  # noqa: E402
from app.middleware.rate_limit import attribution_limiter, devis_limiter  # noqa: E402
from app.models.admin_user import AdminUser  # noqa: E402
from app.services.auth_service import create_access_token  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
API_HEADERS = {"X-API-Key": "test-api-key"}

TABLES = (
    "commissions", "invoice_lines", "customer_invoices", "invoice_sequences", "customers", "attribution_events",
    "attribution_decisions", "leads", "visitors", "devis", "admin_users",
)


def run_alembic(*args: str, database_url: str = TEST_DATABASE_URL) -> None:
    _assert_safe_database(database_url)
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    run_alembic("downgrade", "base")
    run_alembic("upgrade", "head")
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    # DELETE plutôt que TRUNCATE (qui recrée les fichiers de table : très lent sur certains disques).
    # Le rôle "replica" désactive, pour cette seule connexion de test, les triggers d'immuabilité et les FK.
    async with test_engine.begin() as conn:
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        for table in TABLES:
            await conn.execute(text(f"DELETE FROM {table}"))
    devis_limiter.reset()
    attribution_limiter.reset()
    yield


@pytest_asyncio.fixture
async def session():
    async with database.AsyncSessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=API_HEADERS) as c:
        yield c


@pytest_asyncio.fixture
async def admin(session):
    user = AdminUser(email="admin@test.local", hashed_pw="not-used")
    session.add(user)
    await session.commit()
    return user


@pytest_asyncio.fixture
async def admin_client(admin):
    headers = {**API_HEADERS, "Authorization": f"Bearer {create_access_token(str(admin.id))}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as c:
        yield c
