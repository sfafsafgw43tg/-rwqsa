# -*- coding: utf-8 -*-
"""
PrOximAl edit — silnik podmiany tekstu.
Metoda (zgodna z zaleceniami twórców PyMuPDF):
  1. pobierz pełne metadane oryginalnego fragmentu (czcionka, rozmiar, kolor, origin),
  2. spróbuj ponownie użyć czcionki osadzonej w PDF (1:1), w przeciwnym razie
     dobierz najlepiej pasujący font systemowy / wbudowany,
  3. nałóż redakcję (usunięcie starego tekstu) z wypełnieniem= kolor tła (próbkowany),
  4. wstaw nowy tekst w tym samym punkcie bazowym; jeśli nowy tekst jest szerszy,
     czcionka jest automatycznie ZMNIEJSZANA tak, by zmieścić się w starym
     prostokącie => brak nakładania się na sąsiedni tekst.
"""
from __future__ import annotations

import os
import statistics
import tempfile

import pymupdf

from . import fonts as fontmod
from .analyzer import Item

# ----------------------------------------------------------------- tło/colory
def _int_to_rgb(c: int) -> tuple[float, float, float]:
    r = (c >> 16) & 255; g = (c >> 8) & 255; b = c & 255
    return (r / 255, g / 255, b / 255)


def sample_background(page, rect, zoom=3.0, margin=1.5) -> tuple[float, float, float]:
    """Próbkuj kolor tła wokół fragmentu (mediana z pierścienia pikseli)."""
    try:
        clip = (pymupdf.Rect(rect[0] - margin, rect[1] - margin, rect[2] + margin, rect[3] + margin)
                * page.rotation_matrix) & page.rect
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
        w, h, n = pix.width, pix.height, pix.n
        buf = pix.samples
        px = []
        step = max(1, int(zoom))
        # pierścień: górny i dolny wiersz + lewa/prawa kolumna
        for x in range(0, w, step):
            for y in (0, h - 1):
                o = (y * w + x) * n
                px.append((buf[o], buf[o + 1], buf[o + 2]))
        for y in range(0, h, step):
            for x in (0, w - 1):
                o = (y * w + x) * n
                px.append((buf[o], buf[o + 1], buf[o + 2]))
        if not px:
            return (1, 1, 1)
        med = tuple(statistics.median([p[i] for p in px]) / 255 for i in range(3))
        return med
    except Exception:
        return (1, 1, 1)


# --------------------------------------------------------------- czcionki ----
def _try_embedded(page, span, new_text) -> dict | None:
    """Spróbuj wykorzystać czcionkę osadzoną w PDF (subset) — wymaga pokrycia glifów."""
    if span.xref is None:
        return None
    try:
        name, ext, ftype, buf = page.parent.extract_font(span.xref)
        if not buf:
            return None
        cand = fontmod.font_from_buffer(buf)
        if not cand:
            return None
        f = cand["font"]
        for ch in new_text:
            if ord(ch) > 32 and not f.has_glyph(ord(ch)):
                return None
        return cand
    except Exception:
        return None


# --------------------------------------------------------------- przestrzeń --
def free_space_right(page, rect) -> float:
    """Ile wolnego miejsca jest na prawo od prostokąta (do najbliższego elementu w tej samej linii)."""
    try:
        # Glyphs rather than words: in "AB12;next" the separator and the
        # following letters belong to the same PDF word as the edited value.
        from .analyzer import extract_lines
        limit = page.cropbox.width - 2
        for line in extract_lines(page):
            for span in line["spans"]:
                for ch, box in zip(span.text, span.char_rects):
                    x0, y0, x1, y1 = box
                    if ch.isspace() or y1 <= rect[1] or y0 >= rect[3]:
                        continue
                    if x0 >= rect[2] - .05:
                        limit = min(limit, x0 - .3)
        return max(0.0, limit - rect[2])
    except Exception:
        return 0.0



class ReplaceOptions:
    def __init__(self, min_font_size: float = 4.0, allow_expand: bool = False,
                 fill_mode: str = "auto",     # auto | white | none
                 preserve_center: bool = False,
                 use_embedded_fonts: bool = True):
        self.min_font_size = min_font_size
        self.allow_expand = allow_expand
        self.fill_mode = fill_mode
        self.preserve_center = preserve_center
        self.use_embedded_fonts = use_embedded_fonts


# -------------------------------------------------------------- podmiana -----
def _resolve_for_span(page, span, new_text, opts) -> tuple[dict, str]:
    """Zwraca (fontinfo, opis_użytej_czcionki)"""
    if opts.use_embedded_fonts:
        emb = _try_embedded(page, span, new_text)
        if emb:
            return emb, f"osadzona: {emb['font'].name}"
    info = fontmod.resolve_font(span.font, span.flags)
    desc = {"system": "systemowa", "builtin": "wbudowana", "fallback": "zamienna"}.get(info["source"], "?")
    return info, f"{desc}: {info['font'].name}"


def replace_item(page, item: Item, new_value: str, opts: ReplaceOptions) -> dict:
    """Podmienia jeden element na stronie. Zwraca raport częściowy."""
    rep = {"id": item.id, "old": item.value, "new": new_value, "page": item.page,
           "status": "ok", "font": "", "size": None, "shrunk": False}
    rotation = item.rotation
    if rotation is None:
        rep["status"] = "pominięto: dowolny kąt tekstu — dostępny do odczytu"
        return rep
    if not new_value:
        rep["status"] = "pominieto (pusta wartość)"
        return rep
    pieces = [p for p in item.pieces if p.text.strip()]
    if not pieces:
        rep["status"] = "błąd: brak fragmentów"
        return rep
    if len(pieces) > 1:
        # wartość rozbita na kilka spanów — wstawiamy całość w pierwszym,
        # resztę tylko usuwamy (sprawdzamy łączną szerokość)
        pass

    host = pieces[0]
    union = pymupdf.Rect(item.rect)
    # miejsce dostępne dla nowego tekstu: stary obszar (+ ewentualnie wolna przestrzeń na prawo)
    max_width = union.height if rotation in (90, 270) else union.width
    if opts.allow_expand and rotation == 0:
        free = free_space_right(page, tuple(union))
        max_width += min(free, 0.60 * union.width + 12)

    finfo, fdesc = _resolve_for_span(page, host.span, new_value, opts)
    fobj = finfo["font"]
    old_size = host.span.size
    size, shrunk = fontmod.fit_size(fobj, new_value, old_size, max_width, opts.min_font_size)
    if fontmod.text_width(fobj, new_value, size) > max_width + 0.01:
        rep["status"] = "pominięto: tekst nie mieści się przy minimalnej czcionce"
        return rep
    if any(c in new_value for c in "\r\n\t"):
        rep["status"] = "pominięto: wartość musi być w jednym wierszu"
        return rep
    if shrunk:
        rep["shrunk"] = True
        rep["status"] = "ok (zmniejszono czcionkę)"
    rep["font"] = fdesc
    rep["size"] = size

    color = _int_to_rgb(host.span.color)

    # --- 1. wypełnienie tła (próbkowane) ---
    if opts.fill_mode == "white":
        fill = (1, 1, 1)
    elif opts.fill_mode == "none":
        fill = False
    else:
        fill = sample_background(page, union)
        # jeśli tło bardzo ciemne a tekst ciemny -> odwróć (zabezpieczenie)
        lum_bg = sum(fill) / 3
        lum_tx = sum(color) / 3
        if abs(lum_bg - lum_tx) < 0.12:
            fill = (1, 1, 1) if lum_tx < 0.5 else (0, 0, 0)

    # --- 2. redakcje (usunięcie starego tekstu) ---
    is_ocr = getattr(item, "source", "text") == "ocr"
    for p in pieces:
        r = pymupdf.Rect(p.rect)
        if is_ocr:
            # bbox z OCR bywa zbyt ciasny — szerzyj, by usunąć CAŁE stare glify
            r.x0 -= 1.2; r.x1 += 1.2; r.y0 -= 1.4; r.y1 += 1.4
        else:
            # PDF redaction removes an entire glyph on ANY intersection.
            # Full ascender/descender rectangles overlap neighbouring tight
            # rows. Use a central band per span instead, not the full height.
            if rotation in (0, 180):
                middle = (r.y0 + r.y1) / 2
                half = r.height * .12
                r.y0, r.y1 = middle - half, middle + half
                inset = min(.2, r.width * .1)
                r.x0 += inset; r.x1 -= inset
            else:
                middle = (r.x0 + r.x1) / 2
                half = r.width * .12
                r.x0, r.x1 = middle - half, middle + half
                inset = min(.2, r.height * .1)
                r.y0 += inset; r.y1 -= inset
        r = r & pymupdf.Rect(0, 0, page.cropbox.width, page.cropbox.height)
        if not r.is_empty:
            page.add_redact_annot(r, fill=fill)
    img_mode = (pymupdf.PDF_REDACT_IMAGE_PIXELS
                if getattr(item, "source", "text") == "ocr"
                else pymupdf.PDF_REDACT_IMAGE_NONE)
    try:
        page.apply_redactions(images=img_mode,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    except TypeError:
        page.apply_redactions(images=img_mode)

    # --- 3. wstawienie nowego tekstu ---
    # X = LEWA krawędź FRAGMENTU (nie całego spana!), Y = baseline spana
    x, y = host.origin or (min(p.rect[0] for p in pieces), host.span.origin[1])
    if opts.preserve_center:
        w_new = fontmod.text_width(fobj, new_value, size)
        offset = (max_width - w_new) / 2
        x += item.direction[0] * offset
        y += item.direction[1] * offset
    fontname_kwargs = {}
    alias = None
    if finfo.get("buffer") is not None:
        alias = f"PROX{item.id}e"
        page.insert_font(fontname=alias, fontbuffer=finfo["buffer"])
        fontname_kwargs = {"fontname": alias}
    elif finfo.get("fontfile"):
        alias = f"PROX{item.id}s"
        page.insert_font(fontname=alias, fontfile=finfo["fontfile"])
        fontname_kwargs = {"fontname": alias}
    else:
        fontname_kwargs = {"fontname": finfo.get("builtin") or "helv"}

    try:
        rc = page.insert_text(pymupdf.Point(x, y), new_value, fontsize=size,
                              color=color, rotate=rotation, **fontname_kwargs)
        if rc < 0:
            rep["status"] = "ostrzeżenie: część znaków może nie być wyświetlona"
    except Exception as e:
        # awaryjnie base-14
        try:
            page.insert_text(pymupdf.Point(x, y), new_value, fontsize=size,
                             fontname="helv", color=color, rotate=rotation)
            rep["status"] = f"ok (awaryjna czcionka helv; {str(e)[:40]})"
        except Exception as e2:
            rep["status"] = f"błąd wstawienia: {str(e2)[:60]}"
    return rep


def apply_replacements(src_path: str, out_path: str, jobs: list[tuple[Item, str]],
                       opts: ReplaceOptions | None = None, progress=None) -> list[dict]:
    """Otwiera dokument, stosuje wszystkie podmiany, zapisuje do out_path."""
    if os.path.realpath(src_path) == os.path.realpath(out_path):
        raise ValueError("Wynik musi być innym plikiem niż oryginał.")
    opts = opts or ReplaceOptions()
    doc = pymupdf.open(src_path)
    try:
        reports = []
        # grupuj po stronach
        by_page: dict[int, list[tuple[Item, str]]] = {}
        for it, nv in jobs:
            by_page.setdefault(it.page, []).append((it, nv))
        for pno in sorted(by_page.keys()):
            page = doc[pno]
            for it, nv in by_page[pno]:
                reports.append(replace_item(page, it, nv, opts))
                if progress:
                    progress(len(reports), len(jobs))
        # porządkowanie: subset czcionek + zapis
        try:
            doc.subset_fonts()
        except Exception:
            pass
        folder = os.path.dirname(os.path.abspath(out_path))
        fd, temporary = tempfile.mkstemp(suffix=".pdf", dir=folder)
        os.close(fd)
        try:
            doc.save(temporary, garbage=3, deflate=True)
            doc.close()
            os.replace(temporary, out_path)
        finally:
            if not doc.is_closed:
                doc.close()
            if os.path.exists(temporary):
                os.unlink(temporary)
        return reports
    finally:
        if not doc.is_closed:
            doc.close()
