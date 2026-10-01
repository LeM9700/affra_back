import pytest

from app.services.billing_service import compute_invoice_totals
from app.services.commission import compute_commission
from app.schemas.billing import InvoiceLineIn


@pytest.mark.parametrize(
    ("euros", "expected_brackets", "expected_commission_euros"),
    [
        (900, 0, 0),
        (999, 0, 0),
        (1000, 1, 100),
        (1001, 1, 100),
        (1200, 1, 100),
        (1999, 1, 100),
        (2000, 2, 200),
        (2950, 2, 200),
        (2999, 2, 200),
        (3000, 3, 300),
        (4600, 4, 400),
        (7250, 7, 700),
        (10000, 10, 1000),
    ],
)
def test_commission_per_bracket(euros, expected_brackets, expected_commission_euros):
    result = compute_commission(euros * 100)
    assert result.number_of_brackets == expected_brackets
    assert result.commission_amount_cents == expected_commission_euros * 100
    assert result.invoice_amount_cents == euros * 100


def test_commission_cents_just_below_bracket():
    assert compute_commission(99_999).commission_amount_cents == 0
    assert compute_commission(199_999).commission_amount_cents == 10_000


def test_remainders_are_never_carried_over_between_invoices():
    invoice_a = compute_commission(180_000)  # 1 800 €
    invoice_b = compute_commission(150_000)  # 1 500 €
    assert invoice_a.commission_amount_cents == 10_000
    assert invoice_b.commission_amount_cents == 10_000
    assert invoice_a.commission_amount_cents + invoice_b.commission_amount_cents == 20_000
    # Le cumul (3 300 €) donnerait 300 € : ce n'est PAS la règle.
    assert compute_commission(330_000).commission_amount_cents == 30_000


@pytest.mark.parametrize("bad", [0, -100_000])
def test_commission_rejects_non_positive_amounts(bad):
    with pytest.raises(ValueError):
        compute_commission(bad)


@pytest.mark.parametrize("bad", [1000.0, "100000", True, None])
def test_commission_rejects_non_integer_amounts(bad):
    with pytest.raises(TypeError):
        compute_commission(bad)


def test_invoice_totals_use_decimal_and_vat_per_rate():
    lines = [
        InvoiceLineIn(description="Borne 7 kW", quantity="1", unit_price_ht_cents=120_000, vat_rate_bp=550),
        InvoiceLineIn(description="Câble", quantity="12.5", unit_price_ht_cents=1_999, vat_rate_bp=2000),
        InvoiceLineIn(description="Main d'oeuvre", quantity="3", unit_price_ht_cents=6_000, vat_rate_bp=2000),
    ]
    totals = compute_invoice_totals(lines)
    assert totals.line_totals_ht == [120_000, 24_988, 18_000]  # 12.5 × 19.99 = 249.875 → 249.88
    assert totals.total_ht_cents == 162_988
    assert totals.vat_by_rate == {550: (120_000, 6_600), 2000: (42_988, 8_598)}
    assert totals.total_vat_cents == 15_198
    assert totals.total_ttc_cents == 178_186
