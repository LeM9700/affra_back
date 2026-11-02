"""Lecture d'un PDF de facture : texte, bloc client (colonne de droite), tampon « ACQUITTÉE ».

Le logiciel de facturation superpose un tampon diagonal « ACQUITTÉE » en gros caractères : ses
lettres s'intercalent dans le texte. On ne garde que les caractères horizontaux de taille normale,
et l'on signale la présence du tampon (indice de facture payée).
"""

import io
import re
from dataclasses import dataclass

import pdfplumber

MAX_PAGES = 10
# Au-delà, un caractère est considéré comme décoratif (tampon, filigrane).
MAX_TEXT_SIZE = 20
_CLIENT_TITLE = re.compile(r"^(Monsieur|Madame|M\.|Mme|Mlle|Société|SAS|SARL|EURL|SCI|Entreprise)$", re.IGNORECASE)


class UnreadablePdfError(ValueError):
    """Fichier non lisible comme PDF (corrompu, chiffré, vide)."""


@dataclass(frozen=True)
class PdfContent:
    text: str
    client_block: list[str]
    has_text_layer: bool
    paid_stamp: bool
    page_count: int


def _is_body_char(obj: dict) -> bool:
    return obj.get("object_type") != "char" or (obj.get("upright", True) and obj.get("size", 0) < MAX_TEXT_SIZE)


def _client_block(page) -> list[str]:
    """Lignes du destinataire : colonne de droite, à partir de la civilité, jusqu'à 4 lignes."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    half = page.width * 0.4
    start = next((w for w in words if w["x0"] > half and _CLIENT_TITLE.match(w["text"])), None)
    if start is None:
        return []
    column = [w for w in words if w["x0"] >= start["x0"] - 2 and start["top"] - 2 <= w["top"] <= start["top"] + 70]
    lines: dict[int, list[dict]] = {}
    for word in column:
        lines.setdefault(round(word["top"] / 3), []).append(word)
    return [" ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"])) for _, ws in sorted(lines.items())][:4]


def read_pdf(data: bytes) -> PdfContent:
    """Extrait le texte utile d'un PDF de facture.

    Args:
        data: Contenu du fichier PDF.

    Returns:
        Le texte (tampon retiré), le bloc client, et les indices utiles à l'analyse.

    Raises:
        UnreadablePdfError: Si le PDF ne peut pas être ouvert.
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfminer lève des exceptions variées sur un fichier corrompu
        raise UnreadablePdfError("PDF illisible") from exc
    with pdf:
        pages = pdf.pages[:MAX_PAGES]
        if not pages:
            raise UnreadablePdfError("PDF vide")
        paid_stamp = any(not _is_body_char(c) for p in pages for c in p.chars)
        filtered = [p.filter(_is_body_char) for p in pages]
        text = "\n".join(p.extract_text() or "" for p in filtered)
        client = _client_block(filtered[0])
    return PdfContent(
        text=text,
        client_block=client,
        has_text_layer=len(text.strip()) > 50,
        paid_stamp=paid_stamp,
        page_count=len(pages),
    )
