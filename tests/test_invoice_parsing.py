"""Lecture du modèle FAC et contrôles d'une facture importée (fonctions pures, sans base)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.invoice_import.analysis import Draft, DraftLine, LeadContext, analyze, has_blocking
from app.services.invoice_import.template_fac import looks_like_fac_template, parse_fac_text

FIXTURE = (Path(__file__).parent / "fixtures" / "facture_fac_anonymisee.txt").read_text()
CLIENT_BLOCK = ["Madame Jeanne Dupont", "12 RUE DES LILAS", "30700 UZES", "FRANCE"]
AFFRA_SIRET = "98445144300027"


def test_detects_the_fac_template():
    assert looks_like_fac_template(FIXTURE)
    assert not looks_like_fac_template("Facture n° 2026-001 Total : 120 €")


def test_reads_header_client_and_totals():
    inv = parse_fac_text(FIXTURE, CLIENT_BLOCK, paid_stamp=True)
    assert inv.warnings == []
    assert (inv.invoice_number, inv.invoice_date, inv.due_date) == ("FAC00000051", date(2026, 3, 26), date(2026, 3, 26))
    assert (inv.external_quote_ref, inv.external_customer_ref) == ("DEV00000036", "CLT00000025")
    assert (inv.seller_siret, inv.seller_vat_number) == (AFFRA_SIRET, "FR94984451443")
    assert (inv.client_name, inv.client_address_line1, inv.client_postal_code, inv.client_city, inv.client_country) == (
        "Jeanne Dupont",
        "12 RUE DES LILAS",
        "30700",
        "Uzes",
        "France",
    )
    assert (inv.total_ht_cents, inv.total_vat_cents, inv.total_ttc_cents) == (121_000, 6_655, 127_655)
    assert inv.payment_terms == "Virement" and inv.paid_stamp


def test_reads_lines_with_their_multi_line_descriptions():
    lines = parse_fac_text(FIXTURE, CLIENT_BLOCK).lines
    assert [
        (ln.code, ln.quantity, ln.unit, ln.unit_price_ht_cents, ln.discount_bp, ln.total_ht_cents, ln.vat_rate_bp)
        for ln in lines
    ] == [
        ("ART00000048", Decimal("1.00"), "forfait", 110_000, 0, 110_000, 550),
        ("ART00000050", Decimal("1.00"), "u", 6_000, 0, 6_000, 550),
        ("ART00000070", Decimal("1.00"), "u", 5_000, 0, 5_000, 550),
    ]
    first = lines[0].description
    assert first.startswith("Pack Sérénité IRVE (Borne DazeBox Home T\n7,4 kW monophasé")
    assert "au quotidien." in first and "Type de vente" not in first and len(first) <= 2000
    assert lines[2].description == "Module de gestion dynamique de la charge –\nDynamic Power Manager"


def test_missing_parts_are_reported_not_invented():
    inv = parse_fac_text("N° : FAC00000099\nLibellé\nTotal TTC", [])
    assert inv.invoice_number == "FAC00000099"
    assert inv.lines == [] and inv.total_ht_cents is None and inv.client_name is None
    assert any("Bloc client" in w for w in inv.warnings)
    assert any("Aucune ligne" in w for w in inv.warnings)


def test_discounted_line_is_read():
    text = "ART00000001 -Borne 2,00 u 1 000,00 € 10,00% 1 800,00 € 20,00%\nType de vente : x"
    (line,) = parse_fac_text(text, CLIENT_BLOCK).lines
    assert (line.quantity, line.unit_price_ht_cents, line.discount_bp, line.total_ht_cents, line.vat_rate_bp) == (
        Decimal("2.00"),
        100_000,
        1_000,
        180_000,
        2_000,
    )


# ------------------------------------------------------------------ contrôles


def _draft(**overrides) -> Draft:
    inv = parse_fac_text(FIXTURE, CLIENT_BLOCK)
    draft = Draft(
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        client_name=inv.client_name,
        client_postal_code=inv.client_postal_code,
        client_city=inv.client_city,
        lines=[
            DraftLine(ln.quantity, ln.unit_price_ht_cents, ln.discount_bp, ln.vat_rate_bp, ln.total_ht_cents)
            for ln in inv.lines
        ],
        document_total_ht_cents=inv.total_ht_cents,
        document_total_vat_cents=inv.total_vat_cents,
        document_total_ttc_cents=inv.total_ttc_cents,
    )
    for key, value in overrides.items():
        setattr(draft, key, value)
    return draft


def _ctx(**overrides) -> LeadContext:
    ctx = LeadContext(
        prenom="Jeanne",
        nom="Dupont",
        ville="Uzès",
        code_postaux=["30700"],
        villes_devis=[],
        created_on=date(2026, 3, 1),
        today=date(2026, 11, 2),
        seller_siret=AFFRA_SIRET,
        document_seller_siret=AFFRA_SIRET,
        number_taken=False,
        same_amount_same_day=False,
        paid_stamp=True,
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def _levels(checks) -> dict[str, str]:
    return {c.code: c.level for c in checks}


def test_the_sample_invoice_passes_every_check():
    checks = analyze(_draft(), _ctx())
    assert not has_blocking(checks)
    assert all(c.level == "ok" for c in checks), [c for c in checks if c.level != "ok"]
    assert {
        "line_math",
        "vat_rates",
        "total_ht",
        "total_vat",
        "total_ttc",
        "seller",
        "client_name",
        "client_place",
        "number",
        "date",
        "paid",
    } <= set(_levels(checks))


def test_changing_an_amount_away_from_the_pdf_is_blocking():
    """À la confirmation : prix modifié par rapport au PDF → total HT ≠ document → blocage."""
    draft = _draft()
    draft.lines[0] = DraftLine(Decimal("1"), 210_000, 0, 550, None)
    levels = _levels(analyze(draft, _ctx()))
    assert levels["total_ht"] == "blocking" and levels["total_ttc"] == "blocking"


@pytest.mark.parametrize(
    ("ctx_overrides", "draft_overrides", "code", "level"),
    [
        ({"document_seller_siret": "12345678900011"}, {}, "seller", "blocking"),
        ({"document_seller_siret": None}, {}, "seller", "warning"),
        ({"number_taken": True}, {}, "number", "blocking"),
        ({"today": date(2026, 3, 1)}, {}, "date", "blocking"),
        ({"created_on": date(2026, 4, 1)}, {}, "date", "warning"),
        ({"nom": "Martin", "prenom": "Paul"}, {}, "client_name", "warning"),
        ({"nom": "Martin"}, {}, "client_name", "warning"),
        ({"ville": "Nîmes", "code_postaux": ["30000"]}, {}, "client_place", "warning"),
        ({"same_amount_same_day": True}, {}, "duplicate", "warning"),
        ({}, {"invoice_number": None}, "number", "blocking"),
        ({}, {"document_total_vat_cents": 1}, "total_vat", "blocking"),
        ({}, {"document_total_ht_cents": None}, "total_ht", "warning"),
        ({}, {"lines": []}, "lines", "blocking"),
    ],
)
def test_each_inconsistency_is_flagged(ctx_overrides, draft_overrides, code, level):
    assert _levels(analyze(_draft(**draft_overrides), _ctx(**ctx_overrides)))[code] == level


def test_bad_line_math_and_vat_rate_are_blocking():
    draft = _draft(
        lines=[DraftLine(Decimal("2"), 10_000, 0, 1_900, 30_000)],
        document_total_ht_cents=None,
        document_total_vat_cents=None,
        document_total_ttc_cents=None,
    )
    levels = _levels(analyze(draft, _ctx()))
    assert levels["line_math"] == "blocking" and levels["vat_rates"] == "blocking"


def test_name_and_city_matching_ignores_case_accents_and_civility():
    ctx = _ctx(nom="DUPONT", prenom="jeanne", ville="UZES", code_postaux=[])
    levels = _levels(analyze(_draft(client_city="Uzès", client_postal_code="30701"), ctx))
    assert levels["client_name"] == "ok" and levels["client_place"] == "ok"


def test_blocking_checks_come_first():
    checks = analyze(_draft(invoice_number=None), _ctx(created_on=date(2026, 4, 1)))
    assert checks[0].level == "blocking"
    assert [c.level for c in checks] == sorted(
        [c.level for c in checks], key={"blocking": 0, "warning": 1, "ok": 2}.get
    )


# ------------------------------------------------------------------ lecture IA (conversion, sans appel réseau)


def test_ai_output_is_converted_and_flagged_for_review():
    from app.services.invoice_import.ai_extractor import to_extracted

    inv = to_extracted(
        {
            "invoice_number": "F-2026-12",
            "invoice_date": "2026-05-04",
            "due_date": None,
            "seller_siret": "984 451 443 00027",
            "seller_vat_number": None,
            "client_name": "Jeanne Dupont",
            "client_address_line1": "12 rue des Lilas",
            "client_postal_code": "30700",
            "client_city": "Uzès",
            "lines": [
                {
                    "description": "Borne",
                    "quantity": "1",
                    "unit": "u",
                    "unit_price_ht_cents": 100000,
                    "discount_percent": "10",
                    "total_ht_cents": 90000,
                    "vat_rate_percent": "5.5",
                }
            ],
            "total_ht_cents": 90000,
            "total_vat_cents": 4950,
            "total_ttc_cents": 94950,
            "payment_terms": "Virement",
            "paid_stamp": False,
        }
    )
    assert inv.method == "AI" and inv.seller_siret == AFFRA_SIRET
    assert inv.invoice_date == date(2026, 5, 4) and inv.due_date is None
    (line,) = inv.lines
    assert (line.discount_bp, line.vat_rate_bp, line.total_ht_cents) == (1000, 550, 90000)
    assert any("IA" in w for w in inv.warnings)


async def test_ai_extraction_without_key_is_unavailable(monkeypatch):
    from app.config import settings
    from app.services.invoice_import.ai_extractor import AiExtractionUnavailable, extract_with_ai

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(AiExtractionUnavailable):
        await extract_with_ai(b"%PDF-1.4", "application/pdf")
