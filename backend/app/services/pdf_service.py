from __future__ import annotations

import os
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models.entities import DokumentMagazynowy, FakturaVAT

_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _ensure_font() -> tuple[str, str]:
    global _FONT_REGISTERED, _FONT_NAME, _FONT_BOLD
    if _FONT_REGISTERED:
        return _FONT_NAME, _FONT_BOLD

    candidates = [
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf", "ArialPL"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuPL"),
    ]
    for regular_path, bold_path, family in candidates:
        if os.path.exists(regular_path):
            pdfmetrics.registerFont(TTFont(family, regular_path))
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont(f"{family}-Bold", bold_path))
                _FONT_BOLD = f"{family}-Bold"
            else:
                _FONT_BOLD = family
            _FONT_NAME = family
            _FONT_REGISTERED = True
            return _FONT_NAME, _FONT_BOLD

    _FONT_REGISTERED = True
    return _FONT_NAME, _FONT_BOLD


def _safe_text(text: str, font_name: str) -> str:
    if font_name != "Helvetica":
        return text
    # Fallback transliteracji tylko gdy w systemie brak fontu TTF z obsługą polskich znaków
    pl_map = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return text.translate(pl_map)


def render_warehouse_doc_pdf(doc: DokumentMagazynowy, copy_number: int) -> bytes:
    font, font_bold = _ensure_font()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    def txt(x: float, y: float, s: str, bold: bool = False, size: int = 10):
        c.setFont(font_bold if bold else font, size)
        c.drawString(x, y, _safe_text(s, font))

    y = height - 20 * mm
    txt(18 * mm, y, f"E-Magazyn ERP / WMS — Dokument {doc.typ}", bold=True, size=14)
    label = "ORYGINAŁ" if copy_number <= 1 else f"KOPIA (wydruk #{copy_number})"
    c.setFillColor(colors.HexColor("#17365D"))
    txt(145 * mm, y, label, bold=True, size=10)
    c.setFillColor(colors.black)

    y -= 9 * mm
    txt(18 * mm, y, f"Numer dokumentu: {doc.numer}", bold=True, size=11)
    txt(120 * mm, y, f"Status: {doc.status}", size=10)
    y -= 6 * mm
    txt(18 * mm, y, f"Data wystawienia: {doc.data_wystawienia.strftime('%Y-%m-%d %H:%M UTC')}", size=9)
    if doc.kontrahent:
        y -= 6 * mm
        txt(18 * mm, y, f"Kontrahent: {doc.kontrahent.nazwa} (NIP: {doc.kontrahent.nip})", size=9)
        y -= 5 * mm
        txt(18 * mm, y, f"Adres: {doc.kontrahent.adres}", size=9)
    if doc.nr_rejestracyjny:
        y -= 5 * mm
        txt(18 * mm, y, f"Pojazd / transport: {doc.nr_rejestracyjny}", size=9)
    if doc.flaga_awarii_wagi:
        y -= 5 * mm
        c.setFillColor(colors.HexColor("#B91C1C"))
        txt(18 * mm, y, "UWAGA AUDYTOWA: Ręczne wprowadzenie masy przy awarii wagi (autoryzacja KIER_MAG)", bold=True, size=9)
        c.setFillColor(colors.black)

    y -= 10 * mm
    c.line(18 * mm, y, width - 18 * mm, y)
    y -= 6 * mm
    txt(18 * mm, y, "Lp", bold=True, size=9)
    txt(28 * mm, y, "Asortyment", bold=True, size=9)
    txt(95 * mm, y, "Partia", bold=True, size=9)
    txt(135 * mm, y, "Lokalizacja", bold=True, size=9)
    txt(165 * mm, y, "Ilość [kg]", bold=True, size=9)
    y -= 3 * mm
    c.line(18 * mm, y, width - 18 * mm, y)

    for poz in doc.pozycje:
        y -= 6 * mm
        if y < 30 * mm:
            c.showPage()
            y = height - 20 * mm
        txt(18 * mm, y, str(poz.lp), size=9)
        txt(28 * mm, y, poz.asortyment.nazwa[:34], size=9)
        txt(95 * mm, y, poz.partia.kod_partii if poz.partia else "-", size=9)
        txt(135 * mm, y, poz.lokalizacja.kod if poz.lokalizacja else "-", size=9)
        txt(165 * mm, y, f"{poz.ilosc_rozliczeniowa_kg:.3f}", size=9)

    y -= 14 * mm
    if doc.uwagi:
        txt(18 * mm, y, f"Uwagi: {doc.uwagi[:95]}", size=8)
        y -= 10 * mm
    txt(18 * mm, 20 * mm, "Wygenerowano w prototypie E-Magazyn ERP / WMS (dane demonstracyjne).", size=8)

    c.showPage()
    c.save()
    return buf.getvalue()


def render_invoice_pdf(inv: FakturaVAT, copy_number: int) -> bytes:
    font, font_bold = _ensure_font()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    def txt(x: float, y: float, s: str, bold: bool = False, size: int = 10):
        c.setFont(font_bold if bold else font, size)
        c.drawString(x, y, _safe_text(s, font))

    y = height - 20 * mm
    txt(18 * mm, y, f"FAKTURA VAT ({inv.typ})", bold=True, size=15)
    label = "ORYGINAŁ" if copy_number <= 1 else f"KOPIA (wydruk #{copy_number})"
    c.setFillColor(colors.HexColor("#17365D"))
    txt(145 * mm, y, label, bold=True, size=10)
    c.setFillColor(colors.black)

    y -= 9 * mm
    txt(18 * mm, y, f"Numer faktury: {inv.numer}", bold=True, size=11)
    txt(120 * mm, y, f"Status: {inv.status}", size=10)
    y -= 6 * mm
    txt(18 * mm, y, f"Data wystawienia: {inv.data_wystawienia.isoformat()}", size=9)
    txt(90 * mm, y, f"Termin płatności: {inv.termin_platnosci.isoformat()}", size=9)
    txt(150 * mm, y, f"Forma: {inv.forma_platnosci}", size=9)

    y -= 9 * mm
    txt(18 * mm, y, "Sprzedawca: Zakład Młynarsko-Zbożowy E-Magazyn [DEMO], NIP: 0000000000", bold=True, size=9)
    y -= 6 * mm
    txt(18 * mm, y, f"Nabywca: {inv.kontrahent.nazwa} | NIP: {inv.kontrahent.nip}", bold=True, size=9)
    y -= 5 * mm
    txt(18 * mm, y, f"Adres nabywcy: {inv.kontrahent.adres}", size=9)

    y -= 10 * mm
    c.line(18 * mm, y, width - 18 * mm, y)
    y -= 6 * mm
    txt(18 * mm, y, "Lp", bold=True, size=9)
    txt(27 * mm, y, "Towar", bold=True, size=9)
    txt(88 * mm, y, "Ilość [kg]", bold=True, size=9)
    txt(112 * mm, y, "Cena netto", bold=True, size=9)
    txt(138 * mm, y, "VAT", bold=True, size=9)
    txt(153 * mm, y, "Netto [PLN]", bold=True, size=9)
    txt(177 * mm, y, "Brutto [PLN]", bold=True, size=9)
    y -= 3 * mm
    c.line(18 * mm, y, width - 18 * mm, y)

    for poz in inv.pozycje:
        y -= 6 * mm
        if y < 35 * mm:
            c.showPage()
            y = height - 20 * mm
        txt(18 * mm, y, str(poz.lp), size=9)
        txt(27 * mm, y, poz.asortyment.nazwa[:32], size=9)
        txt(88 * mm, y, f"{poz.ilosc_kg:.3f}", size=9)
        txt(112 * mm, y, f"{poz.cena_netto:.3f}", size=9)
        txt(138 * mm, y, f"{poz.stawka_vat:.0f}%", size=9)
        txt(153 * mm, y, f"{poz.wartosc_netto:.2f}", size=9)
        txt(177 * mm, y, f"{poz.wartosc_brutto:.2f}", size=9)

    y -= 10 * mm
    c.line(120 * mm, y, width - 18 * mm, y)
    y -= 6 * mm
    txt(120 * mm, y, f"Razem netto:  {inv.wartosc_netto:.2f} PLN", size=10)
    y -= 5 * mm
    txt(120 * mm, y, f"Kwota VAT:    {inv.wartosc_vat:.2f} PLN", size=10)
    y -= 6 * mm
    txt(120 * mm, y, f"Do zapłaty:   {inv.wartosc_brutto:.2f} PLN", bold=True, size=11)

    txt(18 * mm, 20 * mm, "Dokument wygenerowany w prototypie E-Magazyn ERP / WMS (środowisko demonstracyjne).", size=8)
    c.showPage()
    c.save()
    return buf.getvalue()
