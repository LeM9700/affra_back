"""Contrôles d'une facture importée : cohérence interne et cohérence avec le lead.

Chaque contrôle donne un niveau :
- « ok »       : vérifié ;
- « warning »  : à vérifier, la confirmation exige un motif écrit (conservé) ;
- « blocking » : la facture ne peut pas être enregistrée tant que ce n'est pas corrigé.

Les mêmes contrôles tournent à l'import (sur les données lues) et à la confirmation (sur ce que
l'humain a validé, comparé aux totaux lus dans le PDF) : le montant HT, base de la commission,
ne peut pas s'écarter du document sans blocage.
"""

import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from app.services.billing_service import line_total_ht_cents

Level = Literal["ok", "warning", "blocking"]
ALLOWED_VAT_BP = frozenset({0, 550, 1000, 2000})
# Au-delà, montant inhabituel pour une installation de borne chez un particulier : à vérifier.
UNUSUAL_HT_CENTS = 5_000_000


@dataclass(frozen=True)
class Check:
    code: str
    level: Level
    message: str


@dataclass
class DraftLine:
    quantity: Decimal
    unit_price_ht_cents: int
    discount_bp: int
    vat_rate_bp: int
    # Montant lu sur la facture (None à la confirmation : il est recalculé).
    total_ht_cents: int | None = None


@dataclass
class Draft:
    """Facture à contrôler : lue dans le PDF (import) ou validée par l'humain (confirmation)."""

    invoice_number: str | None
    invoice_date: date | None
    client_name: str | None
    client_postal_code: str | None
    client_city: str | None
    lines: list[DraftLine] = field(default_factory=list)
    # Totaux imprimés sur le PDF : la référence à laquelle tout doit correspondre.
    document_total_ht_cents: int | None = None
    document_total_vat_cents: int | None = None
    document_total_ttc_cents: int | None = None


@dataclass
class LeadContext:
    prenom: str | None
    nom: str | None
    ville: str | None
    code_postaux: list[str]
    villes_devis: list[str]
    created_on: date
    today: date
    seller_siret: str
    document_seller_siret: str | None
    number_taken: bool
    same_amount_same_day: bool
    paid_stamp: bool = False
    extraction_warnings: list[str] = field(default_factory=list)


def _norm(value: str | None) -> str:
    """Minuscules sans accents ni ponctuation, espaces simples (« Saint-Gilles » = « ST GILLES » ≠)."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in ascii_only)
    return " ".join(cleaned.split())


def _euros(cents: int | None) -> str:
    if cents is None:
        return "—"
    return f"{Decimal(cents) / 100:,.2f} €".replace(",", " ").replace(".", ",")


def computed_totals(lines: list[DraftLine]) -> tuple[list[int], int, int]:
    """Totaux recalculés (mêmes règles que la facturation : TVA par taux sur la base cumulée)."""
    line_totals = [line_total_ht_cents(ln.quantity, ln.unit_price_ht_cents, ln.discount_bp) for ln in lines]
    bases: dict[int, int] = {}
    for line, total in zip(lines, line_totals):
        bases[line.vat_rate_bp] = bases.get(line.vat_rate_bp, 0) + total
    vat = sum(
        int((Decimal(base) * rate / 10_000).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))
        for rate, base in bases.items()
    )
    return line_totals, sum(line_totals), vat


def _amount_checks(draft: Draft) -> list[Check]:
    checks: list[Check] = []
    if not draft.lines:
        return [Check("lines", "blocking", "Aucune ligne de facture.")]

    line_totals, total_ht, total_vat = computed_totals(draft.lines)
    wrong_lines = [
        i + 1
        for i, (line, computed) in enumerate(zip(draft.lines, line_totals))
        if line.total_ht_cents is not None and line.total_ht_cents != computed
    ]
    if wrong_lines:
        checks.append(
            Check("line_math", "blocking", f"Montant incohérent (quantité × prix × remise) ligne(s) {wrong_lines}.")
        )
    else:
        checks.append(Check("line_math", "ok", "Montants des lignes cohérents."))

    bad_rates = sorted({ln.vat_rate_bp for ln in draft.lines} - ALLOWED_VAT_BP)
    if bad_rates:
        checks.append(Check("vat_rates", "blocking", f"Taux de TVA non autorisé : {[r / 100 for r in bad_rates]} %."))
    else:
        checks.append(Check("vat_rates", "ok", "Taux de TVA autorisés (0 ; 5,5 ; 10 ; 20 %)."))

    if total_ht <= 0:
        checks.append(Check("amount_positive", "blocking", "Le montant HT doit être strictement positif."))
    elif total_ht > UNUSUAL_HT_CENTS:
        checks.append(Check("amount_unusual", "warning", f"Montant HT inhabituel ({_euros(total_ht)}) : à vérifier."))

    comparisons = (
        ("total_ht", "Total HT", draft.document_total_ht_cents, total_ht),
        ("total_vat", "TVA", draft.document_total_vat_cents, total_vat),
        ("total_ttc", "Total TTC", draft.document_total_ttc_cents, total_ht + total_vat),
    )
    for code, label, printed, computed in comparisons:
        if printed is None:
            checks.append(
                Check(
                    code,
                    "warning",
                    f"{label} non lu sur le document : comparez avec le PDF ({_euros(computed)} calculé).",
                )
            )
        elif printed != computed:
            checks.append(
                Check(
                    code, "blocking", f"{label} du document ({_euros(printed)}) ≠ total calculé ({_euros(computed)})."
                )
            )
        else:
            checks.append(Check(code, "ok", f"{label} conforme au document ({_euros(printed)})."))
    return checks


def _identity_checks(draft: Draft, ctx: LeadContext) -> list[Check]:
    checks: list[Check] = []
    if ctx.document_seller_siret is None:
        checks.append(
            Check(
                "seller",
                "warning",
                "SIRET du vendeur non lu : vérifiez que la facture est bien émise par AFFRA RESEAUX.",
            )
        )
    elif ctx.document_seller_siret != ctx.seller_siret:
        checks.append(
            Check(
                "seller",
                "blocking",
                f"SIRET du vendeur ({ctx.document_seller_siret}) différent de celui d'AFFRA RESEAUX.",
            )
        )
    else:
        checks.append(Check("seller", "ok", "Facture émise par AFFRA RESEAUX (SIRET vérifié)."))

    client = set(_norm(draft.client_name).split())
    lead_tokens = [t for t in (_norm(ctx.nom), _norm(ctx.prenom)) if t]
    if not client:
        checks.append(Check("client_name", "warning", "Nom du client absent de la facture."))
    elif not lead_tokens:
        checks.append(Check("client_name", "warning", "Le lead n'a ni nom ni prénom : rapprochement impossible."))
    else:
        matched = [t for t in lead_tokens if set(t.split()) <= client]
        if _norm(ctx.nom) and _norm(ctx.nom) in matched:
            checks.append(Check("client_name", "ok", f"Client « {draft.client_name} » cohérent avec le lead."))
        elif matched:
            checks.append(
                Check(
                    "client_name",
                    "warning",
                    f"Seul le prénom correspond (« {draft.client_name} ») : vérifiez qu'il s'agit du même client.",
                )
            )
        else:
            lead_name = " ".join(p for p in (ctx.prenom, ctx.nom) if p)
            checks.append(
                Check("client_name", "warning", f"Client « {draft.client_name} » différent du lead « {lead_name} ».")
            )

    city = _norm(draft.client_city)
    known_cities = {_norm(c) for c in [ctx.ville, *ctx.villes_devis] if c}
    if draft.client_postal_code and draft.client_postal_code in ctx.code_postaux:
        checks.append(Check("client_place", "ok", "Code postal identique à celui du devis."))
    elif city and city in known_cities:
        checks.append(Check("client_place", "ok", f"Ville « {draft.client_city} » identique à celle du lead."))
    elif not city:
        checks.append(Check("client_place", "warning", "Ville du client absente de la facture."))
    elif not known_cities and not ctx.code_postaux:
        checks.append(Check("client_place", "warning", "Ville du lead inconnue : rapprochement impossible."))
    else:
        checks.append(Check("client_place", "warning", f"Ville « {draft.client_city} » différente de celle du lead."))
    return checks


def _document_checks(draft: Draft, ctx: LeadContext) -> list[Check]:
    checks: list[Check] = []
    if not draft.invoice_number:
        checks.append(Check("number", "blocking", "Numéro de facture manquant."))
    elif ctx.number_taken:
        checks.append(Check("number", "blocking", f"La facture {draft.invoice_number} est déjà enregistrée."))
    else:
        checks.append(Check("number", "ok", f"Numéro {draft.invoice_number} inédit."))

    if draft.invoice_date is None:
        checks.append(Check("date", "blocking", "Date de facture manquante."))
    elif draft.invoice_date > ctx.today:
        checks.append(Check("date", "blocking", "La date de facture est dans le futur."))
    elif draft.invoice_date < ctx.created_on:
        checks.append(
            Check(
                "date",
                "warning",
                "Facture antérieure à la création du lead : vérifiez que le client vient bien de ce parcours.",
            )
        )
    else:
        checks.append(Check("date", "ok", "Date postérieure à la création du lead."))

    if ctx.same_amount_same_day:
        checks.append(
            Check(
                "duplicate", "warning", "Une facture du même montant existe déjà ce jour-là pour ce client : doublon ?"
            )
        )
    if ctx.paid_stamp:
        checks.append(Check("paid", "ok", "Tampon « ACQUITTÉE » présent : facture payée."))
    for message in ctx.extraction_warnings:
        checks.append(Check("extraction", "warning", message))
    return checks


def analyze(draft: Draft, ctx: LeadContext) -> list[Check]:
    """Tous les contrôles, les bloquants d'abord.

    Args:
        draft: Facture à contrôler.
        ctx: Lead, vendeur et indices de doublon.

    Returns:
        La liste des contrôles.
    """
    checks = _document_checks(draft, ctx) + _amount_checks(draft) + _identity_checks(draft, ctx)
    order = {"blocking": 0, "warning": 1, "ok": 2}
    return sorted(checks, key=lambda c: order[c.level])


def checks_to_json(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]


def has_blocking(checks: list[Check]) -> bool:
    return any(c.level == "blocking" for c in checks)


def warnings_of(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.level == "warning"]
