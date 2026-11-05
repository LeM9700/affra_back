"""Slugs d'URL : même règle que les pages ville du front (/zone-intervention/{slug})."""
import re
import unicodedata

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Convertit un nom de commune en slug ASCII.

    Accents retirés (NFKD), apostrophes et espaces remplacés par des tirets, tirets multiples
    fusionnés.

    Args:
        value: Nom affiché, ex. "Saint-Geniès-de-Malgoirès".

    Returns:
        Slug, ex. "saint-genies-de-malgoires". Chaîne vide si aucun caractère exploitable.

    Example:
        >>> slugify("Le Grau-du-Roi")
        'le-grau-du-roi'
    """
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return _NON_ALNUM.sub("-", ascii_value.lower()).strip("-")
