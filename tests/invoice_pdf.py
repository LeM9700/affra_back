"""Facture PDF FICTIVE au format du logiciel de facturation (modèle FAC), générée pour les tests.

Aucune vraie facture n'est versionnée : la mise en page reproduit seulement ce que la lecture
utilise (vendeur à gauche, client dans la colonne de droite, tableau des lignes, totaux, tampon
« ACQUITTÉE » en diagonal et en gros caractères).
"""

import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

SELLER_LINES = [
    "SARL AFFRA RESEAUX",
    "95 A RUE DE LA HASE",
    "30900 - NIMES",
    "FRANCE",
    "Siret : 98445144300027",
]


def build_invoice_pdf(
    *,
    number: str = "FAC00000077",
    client: tuple[str, ...] = ("Madame", "Jeanne Dupont", "12 RUE DES LILAS", "30700 UZES", "FRANCE"),
    lines: tuple[tuple[str, str, str, str, str, str, str], ...] = (
        (
            "ART00000048 -Pack Sérénité IRVE (Borne DazeBox",
            "1,00",
            "forfait",
            "1 100,00 €",
            "0,00%",
            "1 100,00 €",
            "5,50%",
        ),
        ("ART00000050 -Protections IRVE", "1,00", "u", "110,00 €", "0,00%", "110,00 €", "5,50%"),
    ),
    totals: tuple[str, str, str] = ("1 210,00 €", "66,55 €", "1 276,55 €"),
    paid: bool = True,
    issued_on: date | None = None,
) -> bytes:
    issued = (issued_on or date.today()).strftime("%d/%m/%Y")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setFont("Helvetica", 9)
    y = height - 60
    pdf.drawString(width - 160, y + 15, "FACTURE")
    for i, text in enumerate(SELLER_LINES):
        pdf.drawString(110, y - i * 12, text)
    for i, text in enumerate(
        (f"N° : {number}", f"Date d'émission : {issued}", "En référence : DEV00000036", "N° client : CLT00000099")
    ):
        pdf.drawString(width - 200, y - i * 12, text)

    civility, name, *address = client
    y_client = y - 75
    pdf.drawString(300, y_client, f"{civility} {name}")
    for i, text in enumerate(address, start=1):
        pdf.drawString(300, y_client - i * 12, text)
    pdf.drawString(36, y_client - 12, "Tél. : 07 66 30 46 87")
    pdf.drawString(36, y_client - 24, "Email : affrareseaux@gmail.com")

    y_table = y_client - 90
    pdf.drawString(36, y_table, "Libellé Qté Unité PU HT Rem. Montant HT TVA")
    for i, cells in enumerate(lines, start=1):
        pdf.drawString(36, y_table - i * 14, " ".join(cells))
    y_end = y_table - (len(lines) + 1) * 14
    pdf.drawString(36, y_end, "Type de vente : Vente mixte")
    pdf.drawString(36, y_end - 20, f"Total HT {totals[0]}")
    pdf.drawString(36, y_end - 32, f"TVA {totals[1]}")
    pdf.drawString(36, y_end - 44, f"Total TTC {totals[2]}")
    pdf.drawString(36, y_end - 60, "Règlement Virement")
    pdf.drawString(36, 40, "AFFRA RESEAUX - 95 A RUE DE LA HASE 30900 NIMES FRANCE - N° TVA FR94984451443")

    if paid:
        pdf.saveState()
        pdf.setFont("Helvetica-Bold", 60)
        pdf.translate(width / 2, height / 2)
        pdf.rotate(35)
        pdf.drawCentredString(0, 0, "ACQUITTÉE")
        pdf.restoreState()
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
