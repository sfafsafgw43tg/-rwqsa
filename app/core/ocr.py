# -*- coding: utf-8 -*-
"""
KAMELEON PDF — OCR (opcjonalny, offline).
Dla stron zeskanowanych (bez warstwy tekstu) używa Tesseract (język polski).
Moduł działa tylko, gdy Tesseract jest zainstalowany — instalator BAT
oferuje jego doinstalowanie; bez niego aplikacja działa normalnie,
a strony skanowane są jedynie oznaczane w analizie.
"""
from __future__ import annotations

import shutil

import pymupdf


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_page_text(page, lang: str = "pol", dpi: int = 300) -> str:
    """Zwraca tekst strony z OCR (wymaga tesseract + pytesseract)."""
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("Brak pakietu 'pytesseract'. Zainstaluj: pip install pytesseract")
    if not tesseract_available():
        raise RuntimeError("Nie znaleziono programu Tesseract OCR. Uruchom ponownie instalator i zaznacz OCR.")
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = None
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(pix.tobytes("png")))
    except Exception as e:
        raise RuntimeError(f"Brak biblioteki Pillow: {e}")
    return pytesseract.image_to_string(img, lang=lang)


def ocr_words_with_geometry(page, lang: str = "pol", dpi: int = 300) -> list[dict]:
    """Słowa z OCR + współrzędne (skala pix -> punkty PDF)."""
    try:
        import pytesseract
        from PIL import Image
        import io
    except ImportError:
        raise RuntimeError("Wymagane: pip install pytesseract pillow oraz Tesseract OCR")
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    scale = 72.0 / dpi
    words = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if not t or int(data["conf"][i]) < 35:
            continue
        x, y, w, h = data["left"][i] * scale, data["top"][i] * scale, data["width"][i] * scale, data["height"][i] * scale
        words.append({"text": t, "bbox": (x, y, x + w, y + h), "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i])})
    return words


def ocr_page_to_pdf(page, lang: str = "pol", dpi: int = 300) -> list[dict]:
    """Tworzy 'pseudo-spans' z OCR do analizy (tekst + bbox; czcionka przybliżona)."""
    return ocr_words_with_geometry(page, lang, dpi)


def refine_item_rects(page, items: list, dpi: int = 300, ink_thresh: int = 140,
                      gap_tol_pt: float = 1.8) -> list:
    """
    Doprecyzowuje prostokąty elementów OCR na podstawie pikseli obrazu:
    rozszerzaeach bbox do pełnego, ciągłego atramentu (z tolerancją przerw
    między znakami), dzięki czemu czyszczenie/redakcja obejmuje CAŁY stary tekst.
    """
    if not items:
        return items
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    w, h = pix.width, pix.height
    buf = pix.samples
    scale = dpi / 72.0
    gap_tol = max(1, int(gap_tol_pt * scale))

    def dark(x, y):
        return buf[y * w + x] < ink_thresh

    for it in items:
        try:
            x0, y0, x1, y1 = it.rect
            X0 = max(0, int(x0 * scale) - 3); Y0 = max(0, int(y0 * scale) - 3)
            X1 = min(w - 1, int(x1 * scale) + 3); Y1 = min(h - 1, int(y1 * scale) + 3)

            def col_ink(x, ya, yb):
                return any(buf[y * w + x] < ink_thresh for y in range(ya, yb + 1))

            def row_ink(y, xa, xb):
                return any(buf[y * w + x] < ink_thresh for x in range(xa, xb + 1))

            # horyzontalny spacer od krawędzi seeda, z tolerancją przerw
            lx, gap, x = X0, 0, X0
            while x > 0 and gap <= gap_tol:
                if col_ink(x, Y0, Y1): lx = x; gap = 0
                else: gap += 1
                x -= 1
            rx, gap, x = X1, 0, X1
            while x < w - 1 and gap <= gap_tol:
                if col_ink(x, Y0, Y1): rx = x; gap = 0
                else: gap += 1
                x += 1
            # wertykalny spacer w obrębie [lx, rx]
            ty, gap, y = Y0, 0, Y0
            while y > 0 and gap <= gap_tol:
                if row_ink(y, lx, rx): ty = y; gap = 0
                else: gap += 1
                y -= 1
            by, gap, y = Y1, 0, Y1
            while y < h - 1 and gap <= gap_tol:
                if row_ink(y, lx, rx): by = y; gap = 0
                else: gap += 1
                y += 1

            nrect = (lx / scale, ty / scale, (rx + 1) / scale, (by + 1) / scale)
            it.pieces[0].rect = nrect
            sp = it.pieces[0].span
            sp.bbox = nrect
            nh = nrect[3] - nrect[1]
            sp.size = max(4.0, 0.78 * nh)
            sp.origin = (nrect[0], nrect[3] - 0.22 * nh)
        except Exception:
            continue
    return items
