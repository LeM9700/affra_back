import uuid

from tests.helpers import event, new_vid, submit_devis, visit


async def _prospects(admin_client, **params):
    response = await admin_client.get("/internal/attribution/prospects", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_prospect_is_a_visitor_with_a_contact_action_and_no_lead(client, admin_client):
    visitor_a, visitor_b, visitor_c = new_vid(), new_vid(), new_vid()
    await visit(client, visitor_a, referrer="https://www.google.fr/")
    await event(client, visitor_a, "PHONE_CLICK", page_path="/services/particuliers")
    await event(client, visitor_a, "PHONE_CLICK", page_path="/zone-intervention")
    await event(client, visitor_a, "EMAIL_CLICK", page_path="/")
    await visit(client, visitor_b, referrer="https://chatgpt.com/")  # simple visite : pas un prospect
    await visit(client, visitor_c, utm_source="google_business", utm_medium="organic_local")
    await event(client, visitor_c, "QUOTE_STARTED", page_path="/devis")

    data = await _prospects(admin_client)
    assert data["total"] == 2
    by_source = {p["last_touch"]["source"]: p for p in data["items"]}
    google = by_source["GOOGLE_ORGANIC"]
    assert (google["phone_clicks"], google["email_clicks"], google["events_count"]) == (2, 1, 3)
    assert google["last_event_type"] == "EMAIL_CLICK"
    assert by_source["GOOGLE_BUSINESS"]["quote_started"] == 1
    assert "CHATGPT" not in by_source


async def test_visitor_with_a_devis_is_not_a_prospect(client, admin_client):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.google.fr/")
    await event(client, vid, "PHONE_CLICK")
    await submit_devis(client, vid)
    assert (await _prospects(admin_client))["total"] == 0


async def test_promote_prospect_to_lead_keeps_whole_journey(client, admin_client):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.perplexity.ai/")
    await event(client, vid, "PHONE_CLICK", page_path="/")
    await event(client, vid, "EMAIL_CLICK", page_path="/")
    prospect = (await _prospects(admin_client))["items"][0]

    response = await admin_client.post(
        "/internal/leads",
        json={
            "prenom": "Julie",
            "telephone": "0611223344",
            "visitor_id": prospect["visitor_id"],
            "financial_attribution": "AFFRA_DIGITAL",
            "attribution_confidence": "SUPPORTED",
            "reason": "Appel reçu après clic téléphone depuis Perplexity",
        },
    )
    assert response.status_code == 201, response.text
    lead = response.json()
    assert lead["status"] == "nouveau"
    assert lead["marketing_source"] == "PERPLEXITY"
    assert lead["visitor"]["first_touch"]["source"] == "PERPLEXITY"
    assert sorted(e["event_type"] for e in lead["events"]) == ["EMAIL_CLICK", "LANDING", "PHONE_CLICK"]

    assert (await _prospects(admin_client))["total"] == 0  # il n'est plus un prospect
    again = await admin_client.post(
        "/internal/leads",
        json={
            "nom": "Doublon", "telephone": "0600000000", "visitor_id": prospect["visitor_id"],
            "financial_attribution": "DISPUTED", "attribution_confidence": "UNKNOWN", "reason": "doublon test",
        },
    )
    assert again.status_code == 409


async def test_promote_unknown_prospect_and_exclusive_origins(client, admin_client):
    base = {"nom": "X", "telephone": "0600000000", "financial_attribution": "DISPUTED",
            "attribution_confidence": "UNKNOWN", "reason": "test motif"}
    missing = await admin_client.post("/internal/leads", json={**base, "visitor_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    both = await admin_client.post(
        "/internal/leads", json={**base, "visitor_id": str(uuid.uuid4()), "phone_click_event_id": str(uuid.uuid4())}
    )
    assert both.status_code == 422


async def test_email_click_event_can_also_create_a_lead(client, admin_client):
    vid = new_vid()
    await visit(client, vid, referrer="https://www.bing.com/")
    await event(client, vid, "EMAIL_CLICK")
    # l'API de clics téléphone ne liste que les téléphones ; l'événement email se relie via visitor_id
    assert (await admin_client.get("/internal/attribution/phone-clicks")).json() == []
    prospect = (await _prospects(admin_client))["items"][0]
    assert prospect["email_clicks"] == 1 and prospect["phone_clicks"] == 0


async def test_prospects_filters_pagination_and_auth(client, admin_client):
    for _ in range(3):
        vid = new_vid()
        await visit(client, vid)
        await event(client, vid, "PHONE_CLICK")
    page = await _prospects(admin_client, limit=2)
    assert page["total"] == 3 and len(page["items"]) == 2
    one = await _prospects(admin_client, visitor_id=page["items"][0]["visitor_id"])
    assert one["total"] == 1
    assert (await client.get("/internal/attribution/prospects")).status_code == 401


async def test_client_status_is_automatic_and_locked(client, admin_client):
    from tests.helpers import invoice_payload, lead_id_for_email

    vid = new_vid()
    await visit(client, vid, referrer="https://www.google.fr/")
    await submit_devis(client, vid, email="statut@example.com")
    lead_id = await lead_id_for_email(admin_client, "statut@example.com")

    # « client » ne peut pas être posé à la main
    manual = await admin_client.patch(f"/internal/leads/{lead_id}", json={"status": "client"})
    assert manual.status_code == 422
    assert (await admin_client.patch(f"/internal/leads/{lead_id}", json={"status": "en_cours"})).status_code == 200

    # il vient de la première facture, puis le statut est verrouillé
    assert (await admin_client.post(f"/internal/leads/{lead_id}/invoices", json=invoice_payload(150_000))).status_code == 201
    detail = (await admin_client.get(f"/internal/leads/{lead_id}")).json()
    assert detail["status"] == "client"
    locked = await admin_client.patch(f"/internal/leads/{lead_id}", json={"status": "perdu"})
    assert locked.status_code == 409
    # les coordonnées restent modifiables
    assert (await admin_client.patch(f"/internal/leads/{lead_id}", json={"ville": "Uzès"})).status_code == 200
