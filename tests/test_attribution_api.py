import uuid

from sqlalchemy import func, select

from app.models.attribution import AttributionEvent, Visitor
from tests.helpers import event, new_vid, visit


async def _visitor(session, vid: str) -> Visitor:
    session.expire_all()
    return (await session.execute(select(Visitor).where(Visitor.anonymous_id == uuid.UUID(vid)))).scalar_one()


async def _events(session, vid: str) -> list[AttributionEvent]:
    visitor = await _visitor(session, vid)
    result = await session.execute(
        select(AttributionEvent).where(AttributionEvent.visitor_id == visitor.id).order_by(AttributionEvent.created_at)
    )
    return list(result.scalars())


async def test_visit_creates_visitor_and_landing_event(client, session):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.google.fr/", landing_page="/offres?utm_term=x&email=a@b.fr")

    visitor = await _visitor(session, vid)
    assert visitor.first_source == "GOOGLE_ORGANIC"
    assert visitor.last_source == "GOOGLE_ORGANIC"
    assert visitor.first_landing_page == "/offres"  # paramètres non attributifs supprimés
    assert visitor.first_referrer == "https://www.google.fr/"

    events = await _events(session, vid)
    assert [e.event_type for e in events] == ["LANDING"]
    assert events[0].source == "GOOGLE_ORGANIC"


async def test_first_touch_is_kept_and_last_touch_updated(client, session):
    vid = new_vid()
    await visit(client, vid, referrer="https://chatgpt.com/")                   # jour 1
    await visit(client, vid, referrer="https://www.google.com/")                # jour 3
    visitor = await _visitor(session, vid)
    assert visitor.first_source == "CHATGPT"
    assert visitor.last_source == "GOOGLE_ORGANIC"


async def test_direct_visit_does_not_overwrite_known_last_touch(client, session):
    vid = new_vid()
    await visit(client, vid, utm_source="google_business", utm_medium="organic_local")
    await visit(client, vid)  # retour direct
    visitor = await _visitor(session, vid)
    assert visitor.first_source == "GOOGLE_BUSINESS"
    assert visitor.last_source == "GOOGLE_BUSINESS"
    assert len(await _events(session, vid)) == 2  # la visite directe reste journalisée


async def test_direct_first_visit_then_digital(client, session):
    vid = new_vid()
    await visit(client, vid)
    await visit(client, vid, referrer="https://www.perplexity.ai/search/x")
    visitor = await _visitor(session, vid)
    assert (visitor.first_source, visitor.last_source) == ("DIRECT", "PERPLEXITY")


async def test_utm_has_priority_over_referrer(client, session):
    vid = new_vid()
    await visit(client, vid, utm_source="google_business", utm_medium="organic_local", referrer="https://www.bing.com/")
    assert (await _visitor(session, vid)).first_source == "GOOGLE_BUSINESS"


async def test_bing_and_click_ids(client, session):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.bing.com/")
    await visit(client, vid, gclid="Cj0KCQjw-abc_123")
    visitor = await _visitor(session, vid)
    assert (visitor.first_source, visitor.last_source, visitor.gclid) == ("BING_ORGANIC", "GOOGLE_ADS", "Cj0KCQjw-abc_123")


async def test_visit_is_idempotent_with_client_event_id(client, session):
    vid, ceid = new_vid(), str(uuid.uuid4())
    for _ in range(2):
        response = await client.post(
            "/api/v1/attribution/visit", json={"anonymous_id": vid, "client_event_id": ceid, "landing_page": "/"}
        )
        assert response.status_code == 202
    assert len(await _events(session, vid)) == 1


async def test_phone_click_is_attributed_to_chatgpt(client, session):
    """Parcours B : ChatGPT → site → PHONE_CLICK."""
    vid = new_vid()
    await visit(client, vid, referrer="https://chatgpt.com/", landing_page="/services/particuliers")
    response = await event(client, vid, "PHONE_CLICK", page_path="/services/particuliers", metadata={"placement": "footer"})
    assert response.status_code == 202

    phone_clicks = [e for e in await _events(session, vid) if e.event_type == "PHONE_CLICK"]
    assert len(phone_clicks) == 1
    assert phone_clicks[0].source == "CHATGPT"
    assert phone_clicks[0].page_path == "/services/particuliers"
    assert phone_clicks[0].event_metadata == {"placement": "footer"}


async def test_quote_started_and_email_click(client, session):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.google.fr/")
    assert (await event(client, vid, "QUOTE_STARTED", page_path="/devis")).status_code == 202
    assert (await event(client, vid, "EMAIL_CLICK", page_path="/")).status_code == 202
    types = sorted(e.event_type for e in await _events(session, vid))
    assert types == ["EMAIL_CLICK", "LANDING", "QUOTE_STARTED"]


async def test_event_before_visit_creates_placeholder_visitor(client, session):
    vid = new_vid()
    assert (await event(client, vid, "PHONE_CLICK")).status_code == 202
    visitor = await _visitor(session, vid)
    assert visitor.first_source is None
    # la visite arrivée en retard renseigne bien le first-touch
    await visit(client, vid, referrer="https://claude.ai/")
    visitor = await _visitor(session, vid)
    assert (visitor.first_source, visitor.last_source) == ("CLAUDE", "CLAUDE")


# ------------------------------------------------------------------ Sécurité


async def test_public_endpoints_require_api_key(client):
    response = await client.post(
        "/api/v1/attribution/visit", json={"anonymous_id": new_vid(), "landing_page": "/"}, headers={"X-API-Key": "wrong"}
    )
    assert response.status_code == 403


async def test_rejects_unknown_fields_and_internal_event_types(client):
    vid = new_vid()
    extra = await client.post(
        "/api/v1/attribution/visit", json={"anonymous_id": vid, "landing_page": "/", "source": "CHATGPT"}
    )
    assert extra.status_code == 422
    forged = await client.post(
        "/api/v1/attribution/visit",
        json={"anonymous_id": vid, "landing_page": "/", "financial_attribution": "AFFRA_DIGITAL"},
    )
    assert forged.status_code == 422
    for forbidden_type in ("PHONE_CALL", "QUOTE_SUBMITTED", "LANDING", "ANYTHING"):
        assert (await event(client, vid, forbidden_type)).status_code == 422
    bad_uuid = await client.post("/api/v1/attribution/visit", json={"anonymous_id": "not-a-uuid", "landing_page": "/"})
    assert bad_uuid.status_code == 422
    bad_click_id = await client.post(
        "/api/v1/attribution/visit", json={"anonymous_id": vid, "landing_page": "/", "gclid": "<script>"}
    )
    assert bad_click_id.status_code == 422


async def test_metadata_is_limited(client):
    vid = new_vid()
    too_many = {f"k{i}": i for i in range(11)}
    nested = {"placement": {"a": 1}}
    secret = {"auth_token": "abc"}
    long_value = {"placement": "x" * 201}
    floats = {"value": 1.5}
    for metadata in (too_many, nested, secret, long_value, floats):
        assert (await event(client, vid, "PHONE_CLICK", metadata=metadata)).status_code == 422, metadata
    assert (await event(client, vid, "PHONE_CLICK", metadata={"placement": "cta_band"})).status_code == 202


async def test_oversized_body_is_rejected(client):
    payload = {"anonymous_id": new_vid(), "landing_page": "/" + "a" * 5000}
    response = await client.post("/api/v1/attribution/visit", json=payload)
    assert response.status_code == 413


async def test_attribution_rate_limit_per_client_ip(client, session):
    vid = new_vid()
    for _ in range(60):
        response = await event(client, vid, "PHONE_CLICK")
        assert response.status_code == 202
    blocked = await event(client, vid, "PHONE_CLICK")
    assert blocked.status_code == 429
    # Une autre IP visiteur (transmise par le serveur Next.js) n'est pas impactée.
    other = await client.post(
        "/api/v1/attribution/event",
        json={"anonymous_id": vid, "client_event_id": str(uuid.uuid4()), "event_type": "PHONE_CLICK"},
        headers={"X-Client-IP": "203.0.113.7"},
    )
    assert other.status_code == 202
    count = (await session.execute(select(func.count(AttributionEvent.id)))).scalar_one()
    assert count == 61
