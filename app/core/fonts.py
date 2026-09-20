# -*- coding: utf-8 -*-
"""
PrOximAl edit — silnik dopasowania czcionek.
Dobiera najlepszy możliwy font (TTF z systemu / wbudowany base-14)
do czcionki użytej w oryginalnym dokumencie PDF, zachowując styl
(rodzina, bold, italic, monospace, szeryfowa).
"""
from __future__ import annotations

import os
import re
import platform
import functools

import pymupdf

_SUBSET_RE = re.compile(r"^[A-Z]{6}\+")

# ---------------------------------------------------------------- rodziny ---
# klucz: znormalizowana nazwa rodziny -> kandydaci plików na Windows/Linux/Mac
# warianty: (regular, bold, italic, bold-italic)
FAMILY_MAP = {
    "arial":       "arial",
    "helvetica":   "arial",
    "liberationsans": "arial",
    "arimo":       "arial",
    "sansserif":   "arial",

    "times":       "times",
    "timesnewroman": "times",
    "timesnew":    "times",
    "timesroman":  "times",
    "liberationserif": "times",
    "nimbusroman": "times",
    "tinos":       "times",

    "courier":     "courier",
    "couriernew":  "courier",
    "liberationmono": "courier",
    "nimbusmono":  "courier",
    "cousine":     "courier",
    "monospaced":  "courier",

    "calibri":     "calibri",
    "carlito":     "calibri",
    "segoeui":     "segoeui",
    "segoe":       "segoeui",
    "tahoma":      "tahoma",
    "verdana":     "verdana",
    "dejavusans":  "dejavusans",
    "dejavuserif": "dejavuserif",
    "dejavusansmono": "dejavusansmono",
    "georgia":     "georgia",
    "trebuchetms": "trebuchet",
    "trebuchet":   "trebuchet",
    "comicsansms": "comic",
    "comic":       "comic",
    "impact":      "impact",
    "cambria":     "cambria",
    "caladea":     "cambria",
    "candara":     "candara",
    "corbel":      "corbel",
    "constantia":  "constantia",
    "garamond":    "garamond",
    "ebgaramond":  "garamond",
    "roboto":      "roboto",
    "lato":        "lato",
    "opensans":    "opensans",
    "montserrat":  "montserrat",
    "ptsans":      "pt",
    "notosans":    "noto",
}

# kandydaci plików TTF: rodzina -> [regular, bold, italic, bolditalic]
FILE_CANDIDATES = {
    "arial":     [("arial.ttf", "LiberationSans-Regular.ttf", "Arimo-Regular.ttf", "DejaVuSans.ttf"),
                  ("arialbd.ttf", "LiberationSans-Bold.ttf", "Arimo-Bold.ttf", "DejaVuSans-Bold.ttf"),
                  ("ariali.ttf", "LiberationSans-Italic.ttf", "Arimo-Italic.ttf", "DejaVuSans-Oblique.ttf"),
                  ("arialbi.ttf", "LiberationSans-BoldItalic.ttf", "Arimo-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf")],
    "times":     [("times.ttf", "LiberationSerif-Regular.ttf", "Tinos-Regular.ttf", "DejaVuSerif.ttf"),
                  ("timesbd.ttf", "LiberationSerif-Bold.ttf", "Tinos-Bold.ttf", "DejaVuSerif-Bold.ttf"),
                  ("timesi.ttf", "LiberationSerif-Italic.ttf", "Tinos-Italic.ttf", "DejaVuSerif-Italic.ttf"),
                  ("timesbi.ttf", "LiberationSerif-BoldItalic.ttf", "Tinos-BoldItalic.ttf", "DejaVuSerif-BoldItalic.ttf")],
    "courier":   [("cour.ttf", "LiberationMono-Regular.ttf", "Cousine-Regular.ttf", "DejaVuSansMono.ttf"),
                  ("courbd.ttf", "LiberationMono-Bold.ttf", "Cousine-Bold.ttf", "DejaVuSansMono-Bold.ttf"),
                  ("couri.ttf", "LiberationMono-Italic.ttf", "Cousine-Italic.ttf", "DejaVuSansMono-Oblique.ttf"),
                  ("courbi.ttf", "LiberationMono-BoldItalic.ttf", "Cousine-BoldItalic.ttf", "DejaVuSansMono-BoldOblique.ttf")],
    "calibri":   [("calibri.ttf", "Carlito-Regular.ttf",), ("calibrib.ttf", "Carlito-Bold.ttf",),
                  ("calibrii.ttf", "Carlito-Italic.ttf",), ("calibriz.ttf", "Carlito-BoldItalic.ttf",)],
    "segoeui":   [("segoeui.ttf",), ("segoeuib.ttf",), ("segoeuii.ttf",), ("segoeuiz.ttf",)],
    "tahoma":    [("tahoma.ttf",), ("tahomabd.ttf",), ("tahoma.ttf",), ("tahomabd.ttf",)],
    "verdana":   [("verdana.ttf",), ("verdanab.ttf",), ("verdanai.ttf",), ("verdanaz.ttf",)],
    "dejavusans": [("DejaVuSans.ttf",), ("DejaVuSans-Bold.ttf",), ("DejaVuSans-Oblique.ttf",), ("DejaVuSans-BoldOblique.ttf",)],
    "dejavuserif": [("DejaVuSerif.ttf",), ("DejaVuSerif-Bold.ttf",), ("DejaVuSerif-Italic.ttf",), ("DejaVuSerif-BoldItalic.ttf",)],
    "dejavusansmono": [("DejaVuSansMono.ttf",), ("DejaVuSansMono-Bold.ttf",), ("DejaVuSansMono-Oblique.ttf",), ("DejaVuSansMono-BoldOblique.ttf",)],
    "georgia":   [("georgia.ttf",), ("georgiab.ttf",), ("georgiai.ttf",), ("georgiaz.ttf",)],
    "trebuchet": [("trebuc.ttf",), ("trebucbd.ttf",), ("trebucit.ttf",), ("trebucbi.ttf",)],
    "comic":     [("comic.ttf",), ("comicbd.ttf",), ("comic.ttf",), ("comicbd.ttf",)],
    "impact":    [("impact.ttf",), ("impact.ttf",), ("impact.ttf",), ("impact.ttf",)],
    "cambria":   [("cambria.ttf", "Caladea-Regular.ttf",), ("cambriab.ttf", "Caladea-Bold.ttf",),
                  ("cambriai.ttf", "Caladea-Italic.ttf",), ("cambriaz.ttf", "Caladea-BoldItalic.ttf",)],
    "candara":   [("candara.ttf",), ("candarab.ttf",), ("candarai.ttf",), ("candaraz.ttf",)],
    "corbel":    [("corbel.ttf",), ("corbelb.ttf",), ("corbeli.ttf",), ("corbelz.ttf",)],
    "constantia": [("constan.ttf",), ("constanb.ttf",), ("constani.ttf",), ("constanz.ttf",)],
    "garamond":  [("Garamond.ttf", "EBGaramond-Regular.ttf",), ("Garamond-Bold.ttf", "EBGaramond-Bold.ttf",),
                  ("Garamond-Italic.ttf", "EBGaramond-Italic.ttf",), ("Garamond-BoldItalic.ttf", "EBGaramond-BoldItalic.ttf",)],
    "roboto":    [("Roboto-Regular.ttf",), ("Roboto-Bold.ttf",), ("Roboto-Italic.ttf",), ("Roboto-BoldItalic.ttf",)],
    "lato":      [("Lato-Regular.ttf",), ("Lato-Bold.ttf",), ("Lato-Italic.ttf",), ("Lato-BoldItalic.ttf",)],
    "opensans":  [("OpenSans-Regular.ttf",), ("OpenSans-Bold.ttf",), ("OpenSans-Italic.ttf",), ("OpenSans-BoldItalic.ttf",)],
    "montserrat": [("Montserrat-Regular.ttf",), ("Montserrat-Bold.ttf",), ("Montserrat-Italic.ttf",), ("Montserrat-BoldItalic.ttf",)],
    "pt":        [("PTSans-Regular.ttf", "ptsans_regular.ttf",), ("PTSans-Bold.ttf",), ("PTSans-Italic.ttf",), ("PTSans-BoldItalic.ttf",)],
    "noto":      [("NotoSans-Regular.ttf",), ("NotoSans-Bold.ttf",), ("NotoSans-Italic.ttf",), ("NotoSans-BoldItalic.ttf",)],
}

# awaryjne base-14 (wbudowane w PyMuPDF — zawsze dostępne, pełny offline)
BASE14 = {
    # (rodzina, bold, italic) -> nazwa wbudowana PyMuPDF
    ("arial", False, False): "helv",  ("arial", True, False): "hebo",
    ("arial", False, True): "heit",   ("arial", True, True): "hebi",
    ("times", False, False): "tiro",  ("times", True, False): "tibo",
    ("times", False, True): None,     ("times", True, True): "tibi",
    ("courier", False, False): "cour", ("courier", True, False): "cobo",
    ("courier", False, True): "coit", ("courier", True, True): "cobi",
}
DEFAULT_FALLBACK = "helv"

FONT_DIRS = {
    "Windows": [r"C:\Windows\Fonts"],
    "Linux": ["/usr/share/fonts", "/usr/local/share/fonts",
              os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")],
    "Darwin": ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts",
               os.path.expanduser("~/Library/Fonts")],
}

# nazwa pliku w dokumencie -> lista katalogów do przeszukania
_BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


def _font_dirs():
    dirs = list(FONT_DIRS.get(platform.system(), FONT_DIRS["Linux"]))
    if os.path.isdir(_BUNDLED_DIR):
        dirs.insert(0, _BUNDLED_DIR)
    return dirs


@functools.lru_cache(maxsize=1)
def _scan_fonts() -> dict:
    """mapa: nazwa_pliku_lower (i nazwa bez rozszerzenia) -> pełna ścieżka"""
    found = {}
    for d in _font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf")):
                    p = os.path.join(root, f)
                    found.setdefault(f.lower(), p)
                    found.setdefault(os.path.splitext(f)[0].lower(), p)
    return found


def normalize_font_name(raw: str) -> tuple[str, bool, bool]:
    """'ABCDEF+Arial-BoldMT' -> ('arial', True, False)"""
    name = _SUBSET_RE.sub("", raw or "").strip()
    low = re.sub(r"[^a-z0-9]", "", name.lower())
    bold = "bold" in low or "black" in low or "heavy" in low or low.endswith("-b") or "semibold" in low
    italic = "italic" in low or "oblique" in low
    # usuń sufiksy stylu
    suffixes = ("boldoblique", "bolditalic", "boldmt", "bold", "oblique", "italic",
                "psboldmt", "psmt", "mt", "semibold", "light", "regular", "roman", "narrow", "ps")
    for _ in range(3):  # np. 'timesnewromanpsboldmt' -> 'timesnewromanps' -> 'timesnewroman'
        for suf in suffixes:
            if low.endswith(suf) and len(low) > len(suf):
                low = low[: -len(suf)]
                break
        else:
            break
    family = FAMILY_MAP.get(low, FAMILY_MAP.get(low.rstrip("0123456789"), None))
    if family is None:
        # heurystyki po flagach na zewnątrz (serif/mono) dokonane przez wywołującego
        family = low
    return family, bold, italic


def resolve_font(raw_font_name: str, flags: int = 0) -> dict:
    """
    Zwraca słownik: {family, bold, italic, fontfile (str|None), builtin (str|None),
    font (pymupdf.Font), source: 'system'|'builtin'|'fallback'}
    """
    family, bold, italic = normalize_font_name(raw_font_name)
    bold = bold or bool(flags & 16)
    italic = italic or bool(flags & 2)
    known = family in FILE_CANDIDATES
    if not known:
        # spróbuj po flagach PDF (bit 2 = szeryfowa, bit 3 = mono, bit 4 = bold, bit 1 = italic)
        mono = bool(flags & 8)
        serif = bool(flags & 4)
        bold = bold or bool(flags & 16)
        italic = italic or bool(flags & 2)
        family = "courier" if mono else ("times" if serif else "arial")
        known = True
    idx = (1 if bold else 0) | (2 if italic else 0)
    scan = _scan_fonts()
    for cand in FILE_CANDIDATES.get(family, [[]])[idx]:
        if cand and cand.lower() in scan:
            path = scan[cand.lower()]
            try:
                f = pymupdf.Font(fontfile=path)
                return {"family": family, "bold": bold, "italic": italic,
                        "fontfile": path, "builtin": None, "font": f, "source": "system"}
            except Exception:
                continue
    builtin = BASE14.get((family, bold, italic))
    if builtin:
        try:
            f = pymupdf.Font(builtin)
            return {"family": family, "bold": bold, "italic": italic,
                    "fontfile": None, "builtin": builtin, "font": f, "source": "builtin"}
        except Exception:
            pass
    f = pymupdf.Font(DEFAULT_FALLBACK)
    return {"family": family, "bold": bold, "italic": italic,
            "fontfile": None, "builtin": DEFAULT_FALLBACK, "font": f, "source": "fallback"}


def font_from_buffer(buffer: bytes) -> dict | None:
    """Próba użycia osadzonej (wyekstrahowanej) czcionki 1:1."""
    try:
        f = pymupdf.Font(fontbuffer=buffer)
        return {"family": f.name, "bold": bool(f.flags.get("bold")), "italic": bool(f.flags.get("italic")),
                "fontfile": None, "builtin": None, "font": f, "source": "embedded",
                "buffer": buffer}
    except Exception:
        return None


def text_width(fontobj: "pymupdf.Font", text: str, size: float) -> float:
    try:
        return fontobj.text_length(text, fontsize=size)
    except Exception:
        return pymupdf.get_text_length(text, fontsize=size)


def fit_size(fontobj: "pymupdf.Font", text: str, start_size: float,
             max_width: float, min_size: float = 4.0) -> tuple[float, bool]:
    """Zwraca (rozmiar, czy_zmniejszono) tak, by tekst zmieścił się w max_width."""
    s = start_size
    if text_width(fontobj, text, s) <= max_width or s <= min_size:
        return s, s < start_size - 1e-9
    lo, hi = min_size, s
    for _ in range(24):
        mid = (lo + hi) / 2
        if text_width(fontobj, text, mid) <= max_width:
            lo = mid
        else:
            hi = mid
    return int(lo * 100) / 100, True
