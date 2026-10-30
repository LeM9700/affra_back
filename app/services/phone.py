"""Numéros de téléphone français : normalisation E.164 et affichage.

Le site n'intervient que dans le Gard et l'Hérault : seuls les numéros français sont acceptés.
Le format E.164 (« +33612345678 ») sert de clé de comparaison : la même personne saisit
souvent son numéro de plusieurs façons (« 06 12 34 56 78 », « +33 6 12… », « 0033 6… »).
"""
import re

_SEPARATORS = re.compile(r"[\s.\-()/]")
# Indicatifs français acceptés : 01-05 (fixes), 06-07 (mobiles), 09 (box). 08 = numéros spéciaux.
_NATIONAL = re.compile(r"^0([1-79])(\d{8})$")


class InvalidPhoneError(ValueError):
    """Numéro absent, mal formé ou non français."""


def normalize_french_phone(raw: str) -> str:
    """Convertit une saisie libre en numéro E.164 français.

    Args:
        raw: Numéro tel que saisi par le visiteur.

    Returns:
        Le numéro au format « +33XXXXXXXXX ».

    Raises:
        InvalidPhoneError: Si la saisie n'est pas un numéro français valide.
    """
    compact = _SEPARATORS.sub("", raw or "")
    if compact.startswith("+33"):
        compact = "0" + compact[3:]
    elif compact.startswith("0033"):
        compact = "0" + compact[4:]
    if compact.startswith("00"):
        raise InvalidPhoneError("Numéro étranger non pris en charge")
    match = _NATIONAL.match(compact)
    if match is None:
        raise InvalidPhoneError("Numéro de téléphone français invalide")
    return f"+33{match.group(1)}{match.group(2)}"


def format_french_phone(e164: str | None) -> str:
    """Affiche un numéro E.164 français en « 06 12 34 56 78 » (renvoie la valeur telle quelle sinon).

    Args:
        e164: Numéro au format « +33XXXXXXXXX ».

    Returns:
        Le numéro lisible, ou « — » si absent.
    """
    if not e164:
        return "—"
    if not re.fullmatch(r"\+33\d{9}", e164):
        return e164
    national = "0" + e164[3:]
    return " ".join(national[i : i + 2] for i in range(0, 10, 2))
