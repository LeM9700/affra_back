import uuid

import httpx
import pytest

from app import database
from app.config import settings
from app.models.devis import Devis
from app.services import email_service, notification_service, telegram_service
from tests.helpers import submit_devis

BOT_TOKEN = "123:secret-token"


def _devis(**overrides) -> Devis:
    fields = {
        "id": uuid.uuid4(), "prenom": "Camille", "email": "camille@example.com", "telephone": "0612345678",
        "ville": "Nîmes", "type_client": "maison", "possede_vehicule": "oui", "distance_quotidienne": "0_50",
        "delai": "rapidement", "distance_tableau": "0_5m",
    }
    return Devis(**{**fields, **overrides})


@pytest.fixture
def telegram_configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", "42")


def _mock_telegram(monkeypatch, handler) -> list[httpx.Request]:
    """Route every httpx.AsyncClient through a MockTransport and record the requests."""
    requests: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(recording), **kw)
    )
    return requests


# --- Telegram message ---

def test_message_contains_contact_labels_and_dashboard_link():
    message = telegram_service.format_devis_message(_devis())
    for expected in ("Camille", "0612345678", "camille@example.com", "Nîmes", "Maison", "Rapidement", "0–5 m"):
        assert expected in message
    assert "https://dash-track-affra.netlify.app/" in message


def test_message_tolerates_missing_optional_fields():
    message = telegram_service.format_devis_message(_devis(prenom=None, telephone=None, delai=None))
    assert "👤 —" in message and "Délai : —" in message


# --- Telegram sending ---

async def test_send_skipped_when_not_configured(monkeypatch):
    requests = _mock_telegram(monkeypatch, lambda r: httpx.Response(200, json={"ok": True}))
    await telegram_service.send_devis_notification(_devis())
    assert requests == []


async def test_send_posts_plain_text_to_configured_chat(monkeypatch, telegram_configured):
    requests = _mock_telegram(monkeypatch, lambda r: httpx.Response(200, json={"ok": True}))
    await telegram_service.send_devis_notification(_devis())

    assert len(requests) == 1
    body = httpx.Response(200, content=requests[0].content).json()
    assert requests[0].url.path == f"/bot{BOT_TOKEN}/sendMessage"
    assert body["chat_id"] == "42"
    assert "parse_mode" not in body
    assert "Camille" in body["text"]


async def test_rejection_error_never_leaks_bot_token(monkeypatch, telegram_configured):
    _mock_telegram(monkeypatch, lambda r: httpx.Response(400, json={"ok": False, "description": "chat not found"}))
    with pytest.raises(telegram_service.TelegramNotificationError) as exc_info:
        await telegram_service.send_devis_notification(_devis())
    assert "chat not found" in str(exc_info.value)
    assert BOT_TOKEN not in str(exc_info.value)


async def test_network_error_never_leaks_bot_token(monkeypatch, telegram_configured):
    def unreachable(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    _mock_telegram(monkeypatch, unreachable)
    with pytest.raises(telegram_service.TelegramNotificationError) as exc_info:
        await telegram_service.send_devis_notification(_devis())
    assert BOT_TOKEN not in str(exc_info.value)
    assert exc_info.value.__cause__ is None and exc_info.value.__suppress_context__


# --- Orchestration ---

async def test_one_failing_channel_does_not_block_the_others(monkeypatch):
    called = []

    async def failing(devis):
        called.append("operator_email")
        raise RuntimeError("resend down")

    def ok(name):
        async def send(devis):
            called.append(name)
        return send

    monkeypatch.setattr(email_service, "send_operator_notification", failing)
    monkeypatch.setattr(telegram_service, "send_devis_notification", ok("telegram"))
    monkeypatch.setattr(email_service, "send_prospect_confirmation", ok("prospect_email"))

    await notification_service.notify_new_devis(_devis())
    assert called == ["operator_email", "telegram", "prospect_email"]


async def test_submitting_devis_notifies_only_after_commit(client, monkeypatch):
    seen = []

    async def fake_notify(devis):
        # Session indépendante : ne voit le devis que s'il est déjà commité.
        async with database.AsyncSessionLocal() as other:
            seen.append(await other.get(Devis, devis.id))

    monkeypatch.setattr("app.api.v1.devis.notify_new_devis", fake_notify)
    body = await submit_devis(client)

    assert len(seen) == 1
    assert seen[0] is not None and str(seen[0].id) == body["id"]


# --- Email HTML escaping ---

async def test_operator_email_escapes_user_input(monkeypatch):
    sent = []

    async def capture(params):
        sent.append(params)

    monkeypatch.setattr(settings, "operator_email", "gerant@example.com")
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(email_service, "_send", capture)

    await email_service.send_operator_notification(_devis(prenom='<a href="https://evil.example">Clic</a>'))
    assert "<a href" not in sent[0]["html"]
    assert "&lt;a href=" in sent[0]["html"]
