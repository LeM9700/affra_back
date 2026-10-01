import uuid
from datetime import date

DEVIS_PAYLOAD = {
    "type_client": "maison",
    "possede_vehicule": "oui",
    "distance_quotidienne": "0_50",
    "delai": "rapidement",
    "distance_tableau": "0_5m",
    "prenom": "Camille",
    "email": "camille@example.com",
    "telephone": "0612345678",
    "ville": "Nîmes",
}


def new_vid() -> str:
    return str(uuid.uuid4())


async def visit(client, vid: str, **signals) -> None:
    payload = {"anonymous_id": vid, "landing_page": signals.pop("landing_page", "/"), **signals}
    response = await client.post("/api/v1/attribution/visit", json=payload)
    assert response.status_code == 202, response.text


async def event(client, vid: str, event_type: str, **extra):
    payload = {"anonymous_id": vid, "client_event_id": str(uuid.uuid4()), "event_type": event_type, **extra}
    return await client.post("/api/v1/attribution/event", json=payload)


async def submit_devis(client, vid: str | None = None, **overrides) -> dict:
    payload = {**DEVIS_PAYLOAD, **overrides}
    if vid:
        payload["anonymous_id"] = vid
    response = await client.post("/api/v1/devis", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def invoice_payload(amount_ht_cents: int, number: str | None = None, **overrides) -> dict:
    payload = {
        "invoice_date": date.today().isoformat(),
        "billing": {
            "name": "Camille Martin",
            "address_line1": "12 rue des Lilas",
            "postal_code": "30000",
            "city": "Nîmes",
        },
        "lines": [
            {
                "description": "Installation borne de recharge 7 kW",
                "quantity": "1",
                "unit_price_ht_cents": amount_ht_cents,
                "vat_rate_bp": 2000,
            }
        ],
    }
    if number:
        payload["invoice_number"] = number
    payload.update(overrides)
    return payload


async def lead_id_for_email(admin_client, email: str) -> str:
    response = await admin_client.get("/internal/leads", params={"search": email})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    return items[0]["id"]
