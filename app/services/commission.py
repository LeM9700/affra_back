"""Règle de rémunération de l'acquisition digitale.

100 € de commission par tranche COMPLÈTE de 1 000 € HT, calculée FACTURE PAR FACTURE.
Les reliquats d'une facture ne sont jamais reportés sur une autre facture : la fonction
ne reçoit volontairement qu'un seul montant et n'a aucun état.

Montants en centimes (int) — jamais de float pour l'argent.
"""
from dataclasses import dataclass

BRACKET_CENTS = 100_000          # 1 000,00 €
COMMISSION_PER_BRACKET_CENTS = 10_000  # 100,00 €


@dataclass(frozen=True)
class CommissionComputation:
    invoice_amount_cents: int
    number_of_brackets: int
    commission_amount_cents: int


def compute_commission(invoice_amount_cents: int) -> CommissionComputation:
    if isinstance(invoice_amount_cents, bool) or not isinstance(invoice_amount_cents, int):
        raise TypeError("invoice_amount_cents must be an int (cents)")
    if invoice_amount_cents <= 0:
        raise ValueError("invoice_amount_cents must be > 0")

    number_of_brackets = invoice_amount_cents // BRACKET_CENTS
    return CommissionComputation(
        invoice_amount_cents=invoice_amount_cents,
        number_of_brackets=number_of_brackets,
        commission_amount_cents=number_of_brackets * COMMISSION_PER_BRACKET_CENTS,
    )
