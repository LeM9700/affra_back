"""Import de factures : upload → lecture → contrôles → validation humaine → facture IMPORT."""

import pytest

from app.api.internal.invoice_import_admin import storage_dependency
from app.main import app
from app.services.storage_service import InMemoryStorage
from tests.helpers import new_vid, submit_devis, visit
from tests.invoice_pdf import build_invoice_pdf


@pytest.fixture
def storage():
    mem = InMemoryStorage()
    app.dependency_overrides[storage_dependency] = lambda: mem
    yield mem
    app.dependency_overrides.pop(storage_dependency, None)


async def _lead(client, admin_client, *, prenom="Jeanne", ville="Uzès", digital=True) -> dict:
    vid = new_vid()
    if digital:
        await visit(client, vid, referrer="https://www.google.fr/")
    await submit_devis(client, vid, prenom=prenom, ville=ville, email=f"{prenom.lower()}@example.com")
    lead = (await admin_client.get("/internal/leads")).json()["items"][0]
    patched = await admin_client.patch(f"/internal/leads/{lead['id']}", json={"nom": "Dupont"})
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _upload(admin_client, lead_id: str, data: bytes, filename: str = "facture.pdf"):
    return await admin_client.post(
        f"/internal/leads/{lead_id}/invoice-documents", files={"file": (filename, data, "application/pdf")}
    )


def _levels(document: dict) -> dict[str, str]:
    return {c["code"]: c["level"] for c in document["analysis"]}


async def test_upload_reads_checks_and_stores_the_original(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    pdf = build_invoice_pdf()
    response = await _upload(admin_client, lead["id"], pdf, "FAC 77.pdf")
    assert response.status_code == 201, response.text
    doc = response.json()

    assert (doc["status"], doc["extraction_method"], doc["content_type"]) == (
        "PENDING_REVIEW",
        "PDF_TEXT",
        "application/pdf",
    )
    assert doc["extraction"]["invoice_number"] == "FAC00000077"
    assert doc["extraction"]["total_ht_cents"] == 121_000
    assert all(c["level"] == "ok" for c in doc["analysis"]), doc["analysis"]
    assert _levels(doc)["paid"] == "ok"
    key = f"invoices/{lead['id']}/{doc['sha256']}.pdf"
    assert storage.objects[key] == (pdf, "application/pdf")

    prefill = doc["extraction"]["prefill"]
    assert prefill["billing"]["name"] == "Jeanne Dupont" and prefill["billing"]["postal_code"] == "30700"
    assert [ln["unit_price_ht_cents"] for ln in prefill["lines"]] == [110_000, 11_000]

    url = await admin_client.get(f"/internal/invoice-documents/{doc['id']}/file-url")
    assert url.status_code == 200 and url.json()["url"].startswith("https://storage.test/invoices/")


async def test_same_file_twice_is_refused(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    pdf = build_invoice_pdf()
    first = (await _upload(admin_client, lead["id"], pdf)).json()
    again = await _upload(admin_client, lead["id"], pdf)
    assert again.status_code == 409
    assert again.json()["detail"]["document_id"] == first["id"]


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", 422),
        (b"hello, not a pdf", 415),
        (b"<html><script>alert(1)</script>", 415),
        (b"%PDF-" + b"0" * (10 * 1024 * 1024), 413),
    ],
)
async def test_bad_files_are_refused(client, admin_client, storage, data, code):
    lead = await _lead(client, admin_client)
    assert (await _upload(admin_client, lead["id"], data)).status_code == code
    assert storage.objects == {}


async def test_corrupted_pdf_is_refused(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    assert (await _upload(admin_client, lead["id"], b"%PDF-1.4 garbage without structure")).status_code == 422


async def test_unknown_lead_and_auth(client, admin_client, storage):
    assert (await _upload(admin_client, "00000000-0000-0000-0000-000000000000", build_invoice_pdf())).status_code == 404
    lead = await _lead(client, admin_client)
    anonymous = await client.post(
        f"/internal/leads/{lead['id']}/invoice-documents",
        files={"file": ("f.pdf", build_invoice_pdf(), "application/pdf")},
    )
    assert anonymous.status_code in (401, 403)


async def test_storage_not_configured_gives_503(client, admin_client):
    lead = await _lead(client, admin_client)
    assert (await _upload(admin_client, lead["id"], build_invoice_pdf())).status_code == 503


async def test_image_without_ai_key_falls_back_to_manual_entry(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    doc = (
        await admin_client.post(
            f"/internal/leads/{lead['id']}/invoice-documents", files={"file": ("scan.png", png, "image/png")}
        )
    ).json()
    assert (doc["extraction_method"], doc["content_type"]) == ("NONE", "image/png")
    assert any("saisissez" in c["message"] for c in doc["analysis"])


async def test_confirming_creates_an_imported_invoice_with_its_commission(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf())).json()
    prefill = doc["extraction"]["prefill"]

    confirmed = await admin_client.post(f"/internal/invoice-documents/{doc['id']}/confirm", json={"invoice": prefill})
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["status"] == "CONFIRMED" and result["invoice_id"]

    invoice = (await admin_client.get(f"/internal/invoices/{result['invoice_id']}")).json()
    assert invoice["invoice_number"] == "FAC00000077"
    assert (invoice["total_ht_cents"], invoice["total_vat_cents"], invoice["total_ttc_cents"]) == (
        121_000,
        6_655,
        127_655,
    )
    detail = (await admin_client.get(f"/internal/leads/{lead['id']}")).json()
    assert detail["status"] == "client"
    assert detail["invoices"][0]["commission_amount_cents"] == 10_000  # 1 tranche de 1 000 € HT

    again = await admin_client.post(f"/internal/invoice-documents/{doc['id']}/confirm", json={"invoice": prefill})
    assert again.status_code == 409


async def test_changing_the_amount_away_from_the_pdf_is_blocked(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf())).json()
    prefill = doc["extraction"]["prefill"]
    prefill["lines"][0]["unit_price_ht_cents"] = 210_000  # commission gonflée

    response = await admin_client.post(f"/internal/invoice-documents/{doc['id']}/confirm", json={"invoice": prefill})
    assert response.status_code == 422
    levels = {c["code"]: c["level"] for c in response.json()["detail"]["checks"]}
    assert levels["total_ht"] == "blocking"
    assert (await admin_client.get(f"/internal/invoice-documents/{doc['id']}")).json()["status"] == "PENDING_REVIEW"


async def test_each_accepted_warning_needs_a_written_reason(client, admin_client, storage):
    lead = await _lead(client, admin_client, prenom="Paul", ville="Nîmes")  # nom Dupont, prénom et ville différents
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf())).json()
    assert _levels(doc)["client_place"] == "warning"
    url = f"/internal/invoice-documents/{doc['id']}/confirm"
    prefill = doc["extraction"]["prefill"]

    missing = await admin_client.post(url, json={"invoice": prefill})
    assert missing.status_code == 422
    assert "client_place" in missing.json()["detail"]["missing_acknowledgements"]

    too_short = await admin_client.post(url, json={"invoice": prefill, "acknowledgements": {"client_place": "ok"}})
    assert too_short.status_code == 422

    reason = "Chantier réalisé à Uzès chez sa mère, confirmé par téléphone."
    acks = {code: reason for code in missing.json()["detail"]["missing_acknowledgements"]}
    ok = await admin_client.post(url, json={"invoice": prefill, "acknowledgements": acks})
    assert ok.status_code == 200, ok.text
    assert ok.json()["confirmation"]["acknowledgements"]["client_place"] == reason


async def test_rejected_document_cannot_be_confirmed(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf())).json()
    rejected = await admin_client.post(
        f"/internal/invoice-documents/{doc['id']}/reject", json={"reason": "Mauvais client"}
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert rejected.json()["rejection_reason"] == "Mauvais client"
    confirm = await admin_client.post(
        f"/internal/invoice-documents/{doc['id']}/confirm", json={"invoice": doc["extraction"]["prefill"]}
    )
    assert confirm.status_code == 409
    listed = (await admin_client.get(f"/internal/leads/{lead['id']}/invoice-documents")).json()
    assert [d["status"] for d in listed] == ["REJECTED"]


async def test_number_already_used_by_a_manual_invoice_is_blocking(client, admin_client, storage):
    from tests.helpers import invoice_payload

    lead = await _lead(client, admin_client)
    manual = await admin_client.post(
        f"/internal/leads/{lead['id']}/invoices", json=invoice_payload(50_000, number="FAC00000077")
    )
    assert manual.status_code == 201, manual.text
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf())).json()
    assert _levels(doc)["number"] == "blocking"


async def test_manual_invoice_with_a_line_discount(client, admin_client):
    from tests.helpers import invoice_payload

    lead = await _lead(client, admin_client)
    payload = invoice_payload(100_000)
    payload["lines"][0]["discount_bp"] = 1_000  # remise de 10 %
    created = await admin_client.post(f"/internal/leads/{lead['id']}/invoices", json=payload)
    assert created.status_code == 201, created.text
    invoice = created.json()["invoice"]
    assert invoice["total_ht_cents"] == 90_000
    assert invoice["lines"][0]["discount_bp"] == 1_000


async def test_invoice_older_than_the_lead_needs_a_reason(client, admin_client, storage):
    from datetime import date

    lead = await _lead(client, admin_client)
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf(issued_on=date(2026, 3, 26)))).json()
    assert _levels(doc)["date"] == "warning"


async def test_imported_invoice_exposes_its_origin(client, admin_client, storage):
    lead = await _lead(client, admin_client)
    doc = (await _upload(admin_client, lead["id"], build_invoice_pdf())).json()
    result = (
        await admin_client.post(
            f"/internal/invoice-documents/{doc['id']}/confirm", json={"invoice": doc["extraction"]["prefill"]}
        )
    ).json()
    invoice = (await admin_client.get(f"/internal/invoices/{result['invoice_id']}")).json()
    assert (invoice["source_system"], invoice["external_quote_ref"], invoice["external_customer_ref"]) == (
        "IMPORT",
        "DEV00000036",
        "CLT00000099",
    )
