# -*- coding: utf-8 -*-
"""
PrOximAl edit — OCR (opcjonalny, offline).
Dla stron zeskanowanych (bez warstwy tekstu) używa Tesseract (język polski).
Moduł działa tylko, gdy Tesseract jest zainstalowany — instalator BAT
oferuje jego doinstalowanie; bez niego aplikacja działa normalnie,
a strony skanowane są jedynie oznaczane w analizie.
"""
from __future__ import annotations

import shutil
import os
from pathlib import Path

import pymupdf


def tesseract_available() -> bool:
    import pytesseract
    exe = shutil.which("tesseract")
    if not exe:
        for root in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            candidate = Path(root) / "Tesseract-OCR" / "tesseract.exe"
            if root and candidate.is_file():
                exe = str(candidate)
                break
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    return exe is not None


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
    if not tesseract_available():
        raise RuntimeError("Nie znaleziono Tesseract OCR. Uruchom instalator.")
    if lang not in pytesseract.get_languages(config=""):
        raise RuntimeError(f"Brak języka OCR: {lang}. Doinstaluj pakiet językowy Tesseract.")
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    scale = 72.0 / dpi
    words = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if not t or float(data["conf"][i]) < 35:
            continue
        x, y, w, h = data["left"][i] * scale, data["top"][i] * scale, data["width"][i] * scale, data["height"][i] * scale
        words.append({"text": t, "bbox": (x, y, x + w, y + h), "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i])})
    return words


def ocr_page_to_pdf(page, lang: str = "pol", dpi: int = 300) -> list[dict]:
    """Tworzy 'pseudo-spans' z OCR do analizy (tekst + bbox; czcionka przybliżona)."""
    return ocr_words_with_geometry(page, lang, dpi)


def refine_item_rects(page, items: list, **kwargs) -> list:
    """Keep OCR word bounds; never grow into an adjacent word or table row."""
    return items


def ocr_page_lines(page, lang="pol", dpi=260) -> list[dict]:
    from .analyzer import SpanInfo
    rotation = page.rotation
    page.set_rotation(0)
    try:
        words = ocr_words_with_geometry(page, lang=lang, dpi=dpi)
    finally:
        page.set_rotation(rotation)
    groups = {}
    for word in words:
        groups.setdefault(word["line"], []).append(word)
    result = []
    for words in groups.values():
        spans = []
        for word in sorted(words, key=lambda w: w["bbox"][0]):
            x0, y0, x1, y1 = word["bbox"]
            text = word["text"]
            # OCR has word, not glyph geometry. Proportional character widths
            # stay inside that word; the synthetic separator has zero width.
            font = pymupdf.Font("helv")
            widths = [font.text_length(c) for c in text]
            total = sum(widths) or 1
            x = x0
            rects = []
            for width in widths:
                end = x + (x1 - x0) * width / total
                rects.append((x, y0, end, y1))
                x = end
            rects.append((x1, y0, x1, y1))
            h = max(4, y1 - y0)
            spans.append(SpanInfo(text + " ", (x0, y0, x1, y1),
                                  (x0, y1 - .15 * h), "Helvetica", .85 * h,
                                  0, 0, char_rects=rects))
        bbox = (min(s.bbox[0] for s in spans), min(s.bbox[1] for s in spans),
                max(s.bbox[2] for s in spans), max(s.bbox[3] for s in spans))
        result.append({"text": "".join(s.text for s in spans), "spans": spans,
                       "bbox": bbox, "dir": (1, 0)})
    return sorted(result, key=lambda line: (line["bbox"][1], line["bbox"][0]))
