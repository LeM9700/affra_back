"""E-mail libre du back-office : le message est du texte, jamais du HTML injecté tel quel."""
import pytest

from app.config import settings
from app.services import email_service
from app.services.email_service import text_to_html
from tests.helpers import submit_devis

PAYLOAD = "</script><script>alert(1)</script>"


def test_text_to_html_escapes_tags_and_keeps_line_breaks():
    html = text_to_html(f"Bonjour,\r\n{PAYLOAD}\n<a href=\"https://phish.example\">clic</a>")
    assert "<script" not in html
    assert "<a " not in html
    assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert html.count("<br>") == 2


@pytest.fixture
def captured(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def capture(params: dict) -> None:
        sent.append(params)

    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(email_service, "_send", capture)
    return sent


async def test_custom_email_endpoint_neutralizes_injection(client, admin_client, captured):
    devis = await submit_devis(client)
    response = await admin_client.post(
        f"/internal/devis/{devis['id']}/email",
        json={"subject": "Votre devis\r\nBcc: victime@example.com", "message": f"Bonjour\n{PAYLOAD}"},
    )
    assert response.status_code == 200, response.text
    custom = [m for m in captured if m["subject"].startswith("Votre devis")]
    assert len(custom) == 1
    mail = custom[0]
    assert "<script" not in mail["html"]
    assert "&lt;script&gt;" in mail["html"]
    assert "\n" not in mail["subject"] and "\r" not in mail["subject"]
    assert mail["text"] == f"Bonjour\n{PAYLOAD}"
