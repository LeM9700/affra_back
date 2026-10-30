"""Bouton « Être appelé » : prospect identifié, pages vues, fiche visiteur, passage en lead."""
import uuid

import httpx
import pytest
from sqlalchemy import text

from app import database
from app.config import settings
from app.middleware.rate_limit import telegram_callback_limiter
from tests.helpers import event, new_vid, submit_devis, visit

BOT_TOKEN = "123:secret-token"


def _callback(vid: str, **overrides) -> dict:
    return {
        "anonymous_id": vid,
        "client_event_id": str(uuid.uuid4()),
        "nom": "Camille Martin",
        "telephone": "06 12 34 56 78",
        "consent": True,
        "page_path": "/offres",
        **overrides,
    }


@pytest.fixture
def telegram(monkeypatch) -> list[dict]:
    """Telegram configuré, requêtes interceptées : renvoie les corps JSON envoyés."""
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    sent: list[dict] = []
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    return sent


async def _prospects(admin_client, **params) -> dict:
    response = await admin_client.get("/internal/attribution/prospects", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_callback_makes_an_identified_prospect_not_a_lead(client, admin_client, telegram):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.google.fr/")
    for page in ("/", "/offres", "/services/particuliers"):
        assert (await event(client, vid, "PAGE_VIEW", page_path=page)).status_code == 202
    response = await client.post("/api/v1/attribution/callback", json=_callback(vid))
    assert response.status_code == 202, response.text

    data = await _prospects(admin_client, kind="identified")
    assert data["total"] == 1
    item = data["items"][0]
    assert item["identity"]["name"] == "Camille Martin"
    assert item["identity"]["phone"] == "+33612345678"  # normalisé
    assert (item["page_views"], item["visits"], item["callback_requests"]) == (3, 1, 1)
    assert item["last_event_type"] == "CALLBACK_REQUESTED"

    leads = await admin_client.get("/internal/leads")
    assert leads.json()["total"] == 0  # un prospect identifié n'est pas un lead

    assert len(telegram) == 1
    message = telegram[0]["text"]
    for expected in ("Camille Martin", "06 12 34 56 78", "Google (naturel)", "Pages vues : 3", "/services/particuliers",
                     f"/prospects/{item['visitor_id']}"):
        assert expected in message
    assert "parse_mode" not in telegram[0]


async def test_replayed_callback_is_stored_once_and_notified_once(client, admin_client, telegram):
    vid = new_vid()
    payload = _callback(vid)
    for _ in range(2):
        assert (await client.post("/api/v1/attribution/callback", json=payload)).status_code == 202
    item = (await _prospects(admin_client))["items"][0]
    assert item["callback_requests"] == 1
    assert len(telegram) == 1


async def test_latest_identity_wins(client, admin_client, telegram):
    vid = new_vid()
    await client.post("/api/v1/attribution/callback", json=_callback(vid, telephone="0612345678"))
    await client.post("/api/v1/attribution/callback", json=_callback(vid, nom="Camille Durand", telephone="0700000001"))
    identity = (await _prospects(admin_client))["items"][0]["identity"]
    assert (identity["name"], identity["phone"]) == ("Camille Durand", "+33700000001")


@pytest.mark.parametrize(
    "overrides",
    [
        {"consent": False},
        {"consent": None},
        {"telephone": "08 00 00 00 00"},
        {"telephone": "+44 20 7946 0958"},
        {"nom": "http://spam.example"},
        {"nom": "A"},
        {"is_admin": True},
    ],
)
async def test_invalid_callbacks_are_refused(client, admin_client, overrides):
    vid = new_vid()
    response = await client.post("/api/v1/attribution/callback", json=_callback(vid, **overrides))
    assert response.status_code == 422
    assert (await _prospects(admin_client))["total"] == 0


async def test_missing_consent_is_refused(client):
    payload = _callback(new_vid())
    del payload["consent"]
    assert (await client.post("/api/v1/attribution/callback", json=payload)).status_code == 422


async def test_callback_requires_api_key(client):
    response = await client.post(
        "/api/v1/attribution/callback", json=_callback(new_vid()), headers={"X-API-Key": "wrong"}
    )
    assert response.status_code in (401, 403)


async def test_callback_rate_limited_per_ip(client):
    headers = {"X-Client-IP": "203.0.113.7"}
    codes = [
        (await client.post("/api/v1/attribution/callback", json=_callback(new_vid()), headers=headers)).status_code
        for _ in range(4)
    ]
    assert codes == [202, 202, 202, 429]


async def test_telegram_alerts_are_globally_capped(client, telegram, monkeypatch):
    monkeypatch.setattr(telegram_callback_limiter, "limit", 2)
    for i in range(3):
        headers = {"X-Client-IP": f"203.0.113.{i + 10}"}
        await client.post("/api/v1/attribution/callback", json=_callback(new_vid()), headers=headers)
    assert len(telegram) == 2


async def test_database_refuses_identity_without_consent_or_with_raw_phone(client):
    vid = new_vid()
    await visit(client, vid)
    async with database.AsyncSessionLocal() as session:
        for sql in (
            "UPDATE visitors SET contact_phone = '+33612345678' WHERE anonymous_id = :vid",
            "UPDATE visitors SET contact_phone = '06 12 34 56 78', contact_consent_at = now() "
            "WHERE anonymous_id = :vid",
        ):
            with pytest.raises(Exception):
                await session.execute(text(sql), {"vid": vid})
            await session.rollback()


async def test_search_by_name_or_phone(client, admin_client):
    a, b = new_vid(), new_vid()
    await client.post("/api/v1/attribution/callback", json=_callback(a, nom="Paul Roux", telephone="0611111111"))
    await client.post("/api/v1/attribution/callback", json=_callback(b, nom="Léa Blanc", telephone="0622222222"))
    names = lambda data: [i["identity"]["name"] for i in data["items"]]  # noqa: E731
    assert names(await _prospects(admin_client, search="roux")) == ["Paul Roux"]
    assert names(await _prospects(admin_client, search="06 22 22")) == ["Léa Blanc"]


async def test_visitor_detail_has_the_whole_timeline(client, admin_client):
    vid = new_vid()
    await visit(client, vid, utm_source="google_business", utm_medium="organic_local")
    await event(client, vid, "PAGE_VIEW", page_path="/offres")
    await event(client, vid, "PHONE_CLICK", page_path="/offres")
    await client.post("/api/v1/attribution/callback", json=_callback(vid))
    visitor_id = (await _prospects(admin_client))["items"][0]["visitor_id"]

    response = await admin_client.get(f"/internal/attribution/visitors/{visitor_id}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert [e["event_type"] for e in detail["events"]] == ["CALLBACK_REQUESTED", "PHONE_CLICK", "PAGE_VIEW", "LANDING"]
    assert detail["event_counts"] == {"CALLBACK_REQUESTED": 1, "PHONE_CLICK": 1, "PAGE_VIEW": 1, "LANDING": 1}
    assert detail["identity"]["phone"] == "+33612345678"
    assert detail["first_touch"]["source"] == "GOOGLE_BUSINESS"
    assert detail["lead_id"] is None

    assert (await admin_client.get(f"/internal/attribution/visitors/{uuid.uuid4()}")).status_code == 404
    assert (await client.get(f"/internal/attribution/visitors/{visitor_id}")).status_code in (401, 403)


async def test_identified_prospect_who_sends_a_devis_becomes_a_lead_with_name_and_phone(client, admin_client):
    vid = new_vid()
    await visit(client, vid, referrer="https://chatgpt.com/")
    await client.post("/api/v1/attribution/callback", json=_callback(vid))
    await submit_devis(client, vid, prenom="Camille", telephone="0611111111", email="camille.m@example.com")

    assert (await _prospects(admin_client))["total"] == 0  # il est passé lead
    lead_id = (await admin_client.get("/internal/leads")).json()["items"][0]["id"]
    lead = (await admin_client.get(f"/internal/leads/{lead_id}")).json()
    # Le nom du rappel complète le prénom du devis ; le téléphone saisi dans le devis prime.
    assert (lead["prenom"], lead["nom"], lead["telephone"]) == ("Camille", "Martin", "0611111111")
    assert "CALLBACK_REQUESTED" in [e["event_type"] for e in lead["events"]]

    detail = (await admin_client.get(f"/internal/attribution/visitors/{lead['visitor']['id']}")).json()
    assert detail["lead_id"] == lead_id


async def test_callback_from_an_existing_lead_completes_the_phone_only(client, admin_client, telegram):
    vid = new_vid()
    await visit(client, vid)
    await event(client, vid, "EMAIL_CLICK")
    visitor_id = (await _prospects(admin_client))["items"][0]["visitor_id"]
    created = await admin_client.post(
        "/internal/leads",
        json={"prenom": "Inès", "email": "ines@example.com", "channel": "EMAIL", "visitor_id": visitor_id,
              "financial_attribution": "DISPUTED", "attribution_confidence": "UNKNOWN", "reason": "Email reçu"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["telephone"] is None

    await client.post("/api/v1/attribution/callback", json=_callback(vid, telephone="0699999999"))
    lead = (await admin_client.get(f"/internal/leads/{created.json()['id']}")).json()
    assert lead["telephone"] == "+33699999999"
    assert lead["prenom"] == "Inès"  # rien d'autre n'est écrasé
    assert (await _prospects(admin_client))["total"] == 0
    assert "déjà lead" in telegram[-1]["text"]


def test_split_contact_name():
    from app.services.lead_service import split_contact_name

    assert split_contact_name("Camille Martin", "Camille") == "Martin"
    assert split_contact_name("camille martin", "CAMILLE") == "martin"
    assert split_contact_name("Camille Martin", None) == "Camille Martin"
    assert split_contact_name("Paul Roux", "Camille") is None
    assert split_contact_name("Camille", "Camille") is None
    assert split_contact_name(None, "Camille") is None
