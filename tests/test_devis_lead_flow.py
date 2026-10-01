import uuid

from sqlalchemy import select

from app.models.attribution import AttributionEvent, Visitor
from app.models.devis import Devis
from app.models.lead import Lead
from app.services import lead_service
from tests.helpers import new_vid, submit_devis, visit


async def test_devis_search_does_not_use_removed_nom_column(admin_client, client):
    """Non-régression : la recherche utilisait Devis.nom (supprimé en 0003) → AttributeError / HTTP 500."""
    await submit_devis(client)
    response = await admin_client.get("/internal/devis", params={"search": "camille"})
    assert response.status_code == 200
    assert [d["prenom"] for d in response.json()] == ["Camille"]
    by_phone = await admin_client.get("/internal/devis", params={"search": "0612345678"})
    assert len(by_phone.json()) == 1
    assert (await admin_client.get("/internal/devis", params={"search": "inexistant"})).json() == []


async def test_devis_without_cookie_still_works_and_creates_lead_to_arbitrate(client, session):
    body = await submit_devis(client)
    devis = await session.get(Devis, uuid.UUID(body["id"]))
    lead = await session.get(Lead, devis.lead_id)
    assert lead.visitor_id is None
    assert lead.channel == "FORM"
    assert lead.marketing_source == "UNKNOWN"
    assert (lead.financial_attribution, lead.attribution_confidence) == ("DISPUTED", "UNKNOWN")


async def test_devis_links_visitor_lead_and_quote_submitted(client, session):
    vid = new_vid()
    await visit(client, vid, utm_source="google", utm_medium="organic", landing_page="/?utm_source=google&utm_medium=organic")
    body = await submit_devis(client, vid)

    devis = await session.get(Devis, uuid.UUID(body["id"]))
    lead = await session.get(Lead, devis.lead_id)
    visitor = (await session.execute(select(Visitor).where(Visitor.anonymous_id == uuid.UUID(vid)))).scalar_one()
    assert lead.visitor_id == visitor.id
    assert lead.marketing_source == "GOOGLE_ORGANIC"
    assert (lead.financial_attribution, lead.attribution_confidence) == ("AFFRA_DIGITAL", "SUPPORTED")

    events = (await session.execute(select(AttributionEvent).where(AttributionEvent.lead_id == lead.id))).scalars().all()
    assert sorted(e.event_type for e in events) == ["LANDING", "QUOTE_SUBMITTED"]
    submitted = next(e for e in events if e.event_type == "QUOTE_SUBMITTED")
    assert submitted.devis_id == devis.id
    assert submitted.source == "GOOGLE_ORGANIC"


async def test_second_devis_same_email_reuses_lead_without_touching_decision(client, session):
    first = await submit_devis(client)
    vid = new_vid()
    await visit(client, vid, referrer="https://chatgpt.com/")
    second = await submit_devis(client, vid, email="CAMILLE@example.com")

    d1 = await session.get(Devis, uuid.UUID(first["id"]))
    d2 = await session.get(Devis, uuid.UUID(second["id"]))
    assert d1.lead_id == d2.lead_id
    lead = await session.get(Lead, d1.lead_id)
    assert lead.financial_attribution == "DISPUTED"  # jamais réécrite automatiquement
    assert lead.visitor_id is not None  # le visiteur est désormais rattaché


async def test_attribution_failure_never_breaks_devis(client, session, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("attribution down")

    monkeypatch.setattr(lead_service, "attach_devis_to_lead", boom)
    vid = new_vid()
    body = await submit_devis(client, vid)
    devis = await session.get(Devis, uuid.UUID(body["id"]))
    assert devis is not None
    assert devis.lead_id is None
    assert devis.prenom == "Camille"


async def test_devis_rate_limit_uses_forwarded_client_ip(client):
    for _ in range(5):
        await submit_devis(client, email=f"{uuid.uuid4().hex}@example.com")
    payload_ok = {
        "type_client": "maison", "possede_vehicule": "oui", "distance_quotidienne": "0_50", "delai": "rapidement",
        "distance_tableau": "0_5m", "prenom": "B", "email": "b@example.com", "telephone": "0612345678", "ville": "Alès",
    }
    assert (await client.post("/api/v1/devis", json=payload_ok)).status_code == 429
    other_visitor = await client.post("/api/v1/devis", json=payload_ok, headers={"X-Client-IP": "198.51.100.4"})
    assert other_visitor.status_code == 201
