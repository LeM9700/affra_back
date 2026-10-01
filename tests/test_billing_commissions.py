import uuid
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.billing import Commission, Customer, CustomerInvoice
from app.services import billing_service
from tests.helpers import event, invoice_payload, lead_id_for_email, new_vid, submit_devis, visit


async def _digital_lead(client, admin_client, email="camille@example.com", **visit_signals) -> str:
    vid = new_vid()
    await visit(client, vid, **(visit_signals or {"utm_source": "google", "utm_medium": "organic"}))
    await submit_devis(client, vid, email=email)
    return await lead_id_for_email(admin_client, email)


async def _add_invoice(admin_client, lead_id: str, amount_cents: int, **kwargs):
    return await admin_client.post(f"/internal/leads/{lead_id}/invoices", json=invoice_payload(amount_cents, **kwargs))


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ------------------------------------------------------------------ Parcours de validation


async def test_parcours_a_google_utm_devis_invoice_4600(client, admin_client, session):
    lead_id = await _digital_lead(client, admin_client)
    detail = (await admin_client.get(f"/internal/leads/{lead_id}")).json()
    assert detail["marketing_source"] == "GOOGLE_ORGANIC"
    assert detail["financial_attribution"] == "AFFRA_DIGITAL"
    assert detail["visitor"]["first_touch"]["source"] == "GOOGLE_ORGANIC"
    assert detail["customer"] is None

    response = await _add_invoice(admin_client, lead_id, 460_000)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["customer_created"] is True
    invoice = body["invoice"]
    assert invoice["total_ht_cents"] == 460_000
    assert invoice["total_ttc_cents"] == 552_000
    assert invoice["seller"]["siret"] == "98445144300027"
    assert invoice["commission"]["number_of_brackets"] == 4
    assert invoice["commission"]["commission_amount_cents"] == 40_000
    assert invoice["commission"]["status"] == "DUE"
    assert invoice["invoice_number"] == f"FA-{date.today().year}-0001"

    detail = (await admin_client.get(f"/internal/leads/{lead_id}")).json()
    assert detail["status"] == "client"
    assert detail["customer"]["billing_name"] == "Camille Martin"


async def test_parcours_c_google_business_invoice_2900(client, admin_client):
    lead_id = await _digital_lead(client, admin_client, utm_source="google_business", utm_medium="organic_local")
    detail = (await admin_client.get(f"/internal/leads/{lead_id}")).json()
    assert detail["marketing_source"] == "GOOGLE_BUSINESS"
    invoice = (await _add_invoice(admin_client, lead_id, 290_000)).json()["invoice"]
    assert invoice["commission"]["commission_amount_cents"] == 20_000


async def test_parcours_d_same_customer_two_invoices_no_carry_over(client, admin_client, session):
    lead_id = await _digital_lead(client, admin_client)
    first = (await _add_invoice(admin_client, lead_id, 180_000)).json()
    second = (await _add_invoice(admin_client, lead_id, 150_000)).json()

    assert first["customer_created"] is True
    assert second["customer_created"] is False
    assert first["invoice"]["customer_id"] == second["invoice"]["customer_id"]
    assert await _count(session, Customer) == 1

    assert first["invoice"]["commission"]["commission_amount_cents"] == 10_000
    assert second["invoice"]["commission"]["commission_amount_cents"] == 10_000
    stats = (await admin_client.get("/internal/attribution/stats")).json()
    assert stats["commission_total_cents"] == 20_000  # et surtout PAS 30 000
    assert stats["invoiced_attributed_ht_cents"] == 330_000
    assert stats["brackets_total"] == 2


async def test_parcours_e_invoice_900_creates_customer_with_zero_commission(client, admin_client, session):
    lead_id = await _digital_lead(client, admin_client)
    body = (await _add_invoice(admin_client, lead_id, 90_000)).json()
    assert body["customer_created"] is True
    commission = body["invoice"]["commission"]
    assert (commission["number_of_brackets"], commission["commission_amount_cents"], commission["status"]) == (0, 0, "NOT_DUE")


async def test_parcours_b_phone_lead_linked_to_chatgpt_click(client, admin_client):
    """ChatGPT → site → appel : l'admin crée le lead depuis le clic téléphone enregistré."""
    vid = new_vid()
    await visit(client, vid, referrer="https://chatgpt.com/")
    await event(client, vid, "PHONE_CLICK", page_path="/")

    clicks = (await admin_client.get("/internal/attribution/phone-clicks")).json()
    assert len(clicks) == 1 and clicks[0]["source"] == "CHATGPT"

    response = await admin_client.post(
        "/internal/leads",
        json={
            "prenom": "Sam",
            "telephone": "0611223344",
            "channel": "PHONE",
            "phone_click_event_id": clicks[0]["id"],
            "financial_attribution": "AFFRA_DIGITAL",
            "attribution_confidence": "SUPPORTED",
            "reason": "Appel reçu 2 min après le clic téléphone depuis ChatGPT",
        },
    )
    assert response.status_code == 201, response.text
    lead = response.json()
    assert lead["marketing_source"] == "CHATGPT"
    assert lead["visitor"]["first_touch"]["source"] == "CHATGPT"
    assert any(e["event_type"] == "PHONE_CLICK" for e in lead["events"])
    assert (await admin_client.get("/internal/attribution/phone-clicks")).json() == []

    reuse = await admin_client.post(
        "/internal/leads",
        json={
            "prenom": "Autre", "telephone": "0600000000", "phone_click_event_id": clicks[0]["id"],
            "financial_attribution": "AFFRA_DIGITAL", "attribution_confidence": "SUPPORTED", "reason": "doublon test",
        },
    )
    assert reuse.status_code == 409


async def test_manual_lead_declared_google_business_call(admin_client):
    """Google Business → appel direct (sans visite du site) : source déclarée."""
    response = await admin_client.post(
        "/internal/leads",
        json={
            "nom": "Durand", "telephone": "0466000000", "declared_source": "GOOGLE_BUSINESS",
            "financial_attribution": "AFFRA_DIGITAL", "attribution_confidence": "DECLARED",
            "reason": "Le client dit nous avoir trouvés sur Google Maps",
        },
    )
    assert response.status_code == 201
    lead = response.json()
    assert (lead["marketing_source"], lead["attribution_confidence"], lead["visitor"]) == ("GOOGLE_BUSINESS", "DECLARED", None)


# ------------------------------------------------------------------ Attribution auditable


async def test_attribution_change_is_journaled_and_drives_commissions(client, admin_client, session):
    lead_id = await _digital_lead(client, admin_client)
    invoice = (await _add_invoice(admin_client, lead_id, 250_000)).json()["invoice"]
    assert invoice["commission"]["status"] == "DUE"

    response = await admin_client.post(
        f"/internal/leads/{lead_id}/attribution",
        json={"financial_attribution": "NON_AFFRA", "attribution_confidence": "VERIFIED", "reason": "Client recommandé par un voisin"},
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["financial_attribution"] == "NON_AFFRA"
    decisions = detail["decisions"]
    assert [d["decision"] for d in decisions] == ["NON_AFFRA", "AFFRA_DIGITAL"]  # l'ancienne reste traçable
    assert decisions[0]["previous_decision"] == "AFFRA_DIGITAL"
    assert decisions[0]["created_by_email"] == "admin@test.local"
    assert decisions[1]["created_by"] is None  # décision système initiale
    assert detail["invoices"][0]["commission_status"] == "CANCELLED"

    # Une facture émise sous NON_AFFRA ne génère pas de commission
    other = (await _add_invoice(admin_client, lead_id, 300_000)).json()["invoice"]
    assert other["commission"] is None

    # Retour à AFFRA_DIGITAL : commission réactivée + commission créée pour la facture manquante
    await admin_client.post(
        f"/internal/leads/{lead_id}/attribution",
        json={"financial_attribution": "AFFRA_DIGITAL", "attribution_confidence": "VERIFIED", "reason": "Erreur corrigée"},
    )
    stats = (await admin_client.get("/internal/attribution/stats")).json()
    assert stats["commission_due_cents"] == 20_000 + 30_000
    assert await _count(session, Commission) == 2

    same = await admin_client.post(
        f"/internal/leads/{lead_id}/attribution",
        json={"financial_attribution": "AFFRA_DIGITAL", "attribution_confidence": "VERIFIED", "reason": "identique"},
    )
    assert same.status_code == 409


async def test_paid_commission_is_never_cancelled(client, admin_client):
    lead_id = await _digital_lead(client, admin_client)
    invoice = (await _add_invoice(admin_client, lead_id, 120_000)).json()["invoice"]
    paid = await admin_client.post(f"/internal/commissions/{invoice['commission']['id']}/pay")
    assert paid.status_code == 200 and paid.json()["status"] == "PAID"
    assert (await admin_client.post(f"/internal/commissions/{invoice['commission']['id']}/pay")).status_code == 409

    await admin_client.post(
        f"/internal/leads/{lead_id}/attribution",
        json={"financial_attribution": "DISPUTED", "attribution_confidence": "UNKNOWN", "reason": "Contestation client"},
    )
    commissions = (await admin_client.get("/internal/commissions")).json()["items"]
    assert commissions[0]["status"] == "PAID"
    stats = (await admin_client.get("/internal/attribution/stats")).json()
    assert stats["commission_paid_cents"] == 10_000


async def test_lead_patch_cannot_change_attribution(client, admin_client):
    lead_id = await _digital_lead(client, admin_client)
    response = await admin_client.patch(f"/internal/leads/{lead_id}", json={"financial_attribution": "NON_AFFRA"})
    assert response.status_code == 422
    ok = await admin_client.patch(f"/internal/leads/{lead_id}", json={"nom": "Martin", "status": "en_cours"})
    assert ok.status_code == 200 and ok.json()["nom"] == "Martin"


async def test_decision_journal_is_append_only_in_database(client, admin_client, session):
    await _digital_lead(client, admin_client)
    with pytest.raises(DBAPIError):
        await session.execute(text("UPDATE attribution_decisions SET decision = 'NON_AFFRA'"))
    await session.rollback()


# ------------------------------------------------------------------ Factures


async def test_invoice_amount_validation(client, admin_client):
    lead_id = await _digital_lead(client, admin_client)
    assert (await _add_invoice(admin_client, lead_id, 0)).status_code == 422
    assert (await _add_invoice(admin_client, lead_id, -5)).status_code == 422
    payload = invoice_payload(100_000)
    payload["lines"][0]["unit_price_ht_cents"] = 1000.5
    assert (await admin_client.post(f"/internal/leads/{lead_id}/invoices", json=payload)).status_code == 422
    payload["lines"][0]["unit_price_ht_cents"] = "100000"
    assert (await admin_client.post(f"/internal/leads/{lead_id}/invoices", json=payload)).status_code == 422
    payload = invoice_payload(100_000, lines=[])
    assert (await admin_client.post(f"/internal/leads/{lead_id}/invoices", json=payload)).status_code == 422


async def test_duplicate_invoice_number_rejected_without_partial_customer(client, admin_client, session):
    lead_a = await _digital_lead(client, admin_client, email="a@example.com")
    lead_b = await _digital_lead(client, admin_client, email="b@example.com")
    assert (await _add_invoice(admin_client, lead_a, 150_000, number="F-2026-001")).status_code == 201

    duplicate = await _add_invoice(admin_client, lead_b, 150_000, number="F-2026-001")
    assert duplicate.status_code == 409
    session.expire_all()
    assert await _count(session, Customer) == 1  # pas de Customer orphelin pour le lead B
    assert await _count(session, CustomerInvoice) == 1
    assert await _count(session, Commission) == 1


async def test_invoice_creation_is_atomic(client, admin_client, session, monkeypatch):
    lead_id = await _digital_lead(client, admin_client)

    def fail(*args, **kwargs):
        raise RuntimeError("commission storage failure")

    monkeypatch.setattr(billing_service, "build_commission", fail)
    with pytest.raises(RuntimeError):
        await _add_invoice(admin_client, lead_id, 200_000)
    session.expire_all()
    assert await _count(session, Customer) == 0
    assert await _count(session, CustomerInvoice) == 0
    assert await _count(session, Commission) == 0


async def test_invoices_are_immutable_in_database(client, admin_client, session):
    lead_id = await _digital_lead(client, admin_client)
    await _add_invoice(admin_client, lead_id, 150_000)
    with pytest.raises(DBAPIError):
        await session.execute(text("UPDATE customer_invoices SET total_ht_cents = 999999"))
    await session.rollback()
    with pytest.raises(DBAPIError):
        await session.execute(text("DELETE FROM customer_invoices"))
    await session.rollback()
    with pytest.raises(DBAPIError):
        await session.execute(text("UPDATE commissions SET commission_amount_cents = 50000, number_of_brackets = 5"))
    await session.rollback()


async def test_commission_rule_enforced_by_database(admin_client, session):
    lead = await admin_client.post(
        "/internal/leads",
        json={"nom": "Non digital", "telephone": "0600000001", "financial_attribution": "NON_AFFRA",
              "attribution_confidence": "VERIFIED", "reason": "Client historique"},
    )
    invoice = (await _add_invoice(admin_client, lead.json()["id"], 150_000)).json()["invoice"]
    assert invoice["commission"] is None
    # Insertion directe falsifiée : 1 500 € HT déclarés avec 2 tranches.
    with pytest.raises(DBAPIError, match="ck_commissions_brackets_rule"):
        await session.execute(
            text(
                "INSERT INTO commissions (id, invoice_id, invoice_amount_cents, number_of_brackets, commission_amount_cents, status) "
                "VALUES (gen_random_uuid(), :id, 150000, 2, 20000, 'DUE')"
            ),
            {"id": uuid.UUID(invoice["id"])},
        )
    await session.rollback()


async def test_lists_and_stats(client, admin_client):
    lead_id = await _digital_lead(client, admin_client)
    await _add_invoice(admin_client, lead_id, 460_000)
    await submit_devis(client, email="direct@example.com")  # lead à arbitrer, sans facture

    leads = (await admin_client.get("/internal/leads", params={"limit": 1})).json()
    assert leads["total"] == 2 and len(leads["items"]) == 1
    filtered = (await admin_client.get("/internal/leads", params={"financial_attribution": "AFFRA_DIGITAL"})).json()
    assert filtered["total"] == 1 and filtered["items"][0]["customer_id"] is not None

    invoices = (await admin_client.get("/internal/invoices")).json()
    assert invoices["total"] == 1 and invoices["items"][0]["commission_amount_cents"] == 40_000
    invoice_id = invoices["items"][0]["id"]
    full = (await admin_client.get(f"/internal/invoices/{invoice_id}")).json()
    assert full["lines"][0]["description"].startswith("Installation")
    assert full["vat_breakdown"] == [{"vat_rate_bp": 2000, "base_ht_cents": 460_000, "vat_cents": 92_000}]

    commissions = (await admin_client.get("/internal/commissions", params={"status": "DUE"})).json()
    assert commissions["items"][0]["marketing_source"] == "GOOGLE_ORGANIC"
    assert commissions["items"][0]["number_of_brackets"] == 4

    stats = (await admin_client.get("/internal/attribution/stats")).json()
    assert stats["leads_total"] == 2
    assert stats["leads_digital"] == 1
    assert stats["leads_to_arbitrate"] == 1
    assert stats["customers_digital"] == 1
    assert stats["invoices_attributed"] == 1
    assert stats["commission_due_cents"] == 40_000
    assert stats["commission_paid_cents"] == 0
    assert {"source": "GOOGLE_ORGANIC", "count": 1} in stats["leads_by_source"]


# ------------------------------------------------------------------ Sécurité des endpoints internes


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/internal/leads"),
        ("get", f"/internal/leads/{uuid.uuid4()}"),
        ("post", f"/internal/leads/{uuid.uuid4()}/invoices"),
        ("post", f"/internal/leads/{uuid.uuid4()}/attribution"),
        ("get", "/internal/invoices"),
        ("get", "/internal/commissions"),
        ("post", f"/internal/commissions/{uuid.uuid4()}/pay"),
        ("get", "/internal/attribution/stats"),
        ("get", "/internal/attribution/phone-clicks"),
    ],
)
async def test_internal_endpoints_require_jwt(client, method, path):
    response = await getattr(client, method)(path)
    assert response.status_code == 401


async def test_internal_endpoints_require_api_key(admin_client):
    response = await admin_client.get("/internal/leads", headers={"X-API-Key": "wrong"})
    assert response.status_code == 403


async def test_unknown_lead_returns_404(admin_client):
    assert (await admin_client.post(f"/internal/leads/{uuid.uuid4()}/invoices", json=invoice_payload(100_000))).status_code == 404
