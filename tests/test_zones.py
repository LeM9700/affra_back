"""Zones : slug de liaison avec les pages ville du front."""
import pytest
from sqlalchemy import text

from app.services.slug import slugify
from tests.conftest import API_HEADERS, test_engine


@pytest.mark.parametrize(
    ("ville", "slug"),
    [
        ("Saint-Geniès-de-Malgoirès", "saint-genies-de-malgoires"),
        ("Le Grau-du-Roi", "le-grau-du-roi"),
        ("Nîmes", "nimes"),
        ("  Aimargues ", "aimargues"),
        ("L'Isle-sur-la-Sorgue", "l-isle-sur-la-sorgue"),
        ("Sète", "sete"),
    ],
)
def test_slugify_matches_front_slugs(ville, slug):
    assert slugify(ville) == slug


async def test_create_zone_derives_slug_and_exposes_it_publicly(client):
    created = await client.post("/internal/zones", json={"ville": "Aimargues", "departement": "30"}, headers=API_HEADERS)
    assert created.status_code == 201, created.text
    assert created.json()["slug"] == "aimargues"

    public = await client.get("/api/v1/zones", headers=API_HEADERS)
    assert [z["slug"] for z in public.json()] == ["aimargues"]


async def test_explicit_slug_is_kept(client):
    created = await client.post(
        "/internal/zones", json={"ville": "Nimes", "slug": "nimes", "departement": "30"}, headers=API_HEADERS
    )
    assert created.json()["slug"] == "nimes"


async def test_duplicate_slug_returns_409(client):
    body = {"ville": "Uzès", "departement": "30"}
    assert (await client.post("/internal/zones", json=body, headers=API_HEADERS)).status_code == 201
    duplicate = await client.post("/internal/zones", json={**body, "ville": "Uzes"}, headers=API_HEADERS)
    assert duplicate.status_code == 409


async def test_invalid_slug_is_rejected(client):
    response = await client.post(
        "/internal/zones", json={"ville": "Alès", "slug": "Alès <x>", "departement": "30"}, headers=API_HEADERS
    )
    assert response.status_code == 422


async def test_update_slug(client):
    zone = (await client.post("/internal/zones", json={"ville": "Ales", "departement": "30"}, headers=API_HEADERS)).json()
    updated = await client.put(f"/internal/zones/{zone['id']}", json={"slug": "ales"}, headers=API_HEADERS)
    assert updated.status_code == 200
    async with test_engine.connect() as conn:
        assert (await conn.execute(text("SELECT slug FROM zones"))).scalar() == "ales"
