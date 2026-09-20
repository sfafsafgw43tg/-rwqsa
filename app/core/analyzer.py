# -*- coding: utf-8 -*-
"""
PrOximAl edit — analizator dokumentu.
Uwzględnia każdy niepusty fragment warstwy tekstowej PDF.
Kategorie są podpowiedziami, a nie filtrem decydującym o widoczności.
Z linii tekstu PDF (z dokładnym położeniem, czcionką, kolorem) klasyfikuje:
  • imiona i nazwiska (heurystyka + etykiety),
  • wszystkie numery (kwoty, PESEL, NIP, REGON, telefony, konta, numery faktur...),
  • daty (numeryczne i polskie słowne),
  • opisy/etykiety ("za co" dana wartość odpowiada).
Linie o tej samej linii bazowej są scalane w wiersze (poprawne etykiety
w układach wielokolumnowych, np. faktur).
"""
from __future__ import annotations

import re
import uuid
import math
from dataclasses import dataclass, field

import pymupdf

from .dates import find_dates, DateHit
from . import fonts as fontmod
from . import classification as classes

# ------------------------------------------------------------------ modele --
@dataclass
class SpanInfo:
    text: str
    bbox: tuple
    origin: tuple
    font: str
    size: float
    color: int
    flags: int
    xref: int | None = None
    char_rects: list[tuple] = field(default_factory=list)
    char_origins: list[tuple] = field(default_factory=list)
    ocr_confidence: float | None = None

@dataclass
class Piece:
    """Fragment wartości w obrębie jednego spana (do redakcji + wstawienia)."""
    span: SpanInfo
    text: str
    rect: tuple
    origin: tuple | None = None

@dataclass
class Item:
    id: str
    type: str              # 'data','kwota','PESEL','NIP','REGON','telefon','nr konta','kod pocztowy','numer','procent','imię i nazwisko','nazwisko','ulica nr'
    value: str
    label: str
    page: int
    pieces: list[Piece] = field(default_factory=list)
    date_hit: DateHit | None = None
    new_value: str = ""
    enabled: bool = True
    score: float = 0.0
    source: str = "text"   # 'text' | 'ocr' 

    direction: tuple = (1, 0)

    @property
    def rotation(self):
        for vector, rotation in [((1, 0), 0), ((0, -1), 90), ((-1, 0), 180), ((0, 1), 270)]:
            if all(math.isclose(a, b, abs_tol=1e-4) for a, b in zip(self.direction, vector)):
                return rotation
        return None

    @property
    def ocr_confidence(self):
        scores = [piece.span.ocr_confidence for piece in self.pieces if piece.span.ocr_confidence is not None]
        return min(scores) if scores else None

    @property
    def editable(self):
        return self.rotation is not None

    @property
    def rect(self):
        x0 = min(p.rect[0] for p in self.pieces); y0 = min(p.rect[1] for p in self.pieces)
        x1 = max(p.rect[2] for p in self.pieces); y1 = max(p.rect[3] for p in self.pieces)
        return (x0, y0, x1, y1)

    @property
    def font_desc(self) -> str:
        s = self.pieces[0].span
        return f"{s.font} @ {round(s.size, 1)}pt"

# ----------------------------------------------------------------- słowniki --
NAME_LABELS = ["imię", "imie", "imiona", "nazwisko", "imię i nazwisko", "imie i nazwisko",
               "name", "first name", "last name", "full name", "właściciel", "wlasciciel",
               "klient", "zamawiający", "zamawiajacy", "wykonawca", "sprzedawca", "nabywca",
               "pracownik", "zleceniobiorca", "zleceniodawca", "ubezpieczony", "pacjent",
               "pasażer", "pasazer", "kupujący", "kupujacy", "sprzedający", "sprzedajacy",
               "odbiorca", "nadawca", "deklarant", "kierowca", "lekarz", "podpisał"]

STOPWORDS = {
    "faktura", "faktury", "umowa", "umowy", "zlecenie", "zlecenia", "data", "daty", "strona",
    "kwota", "kwoty", "razem", "netto", "brutto", "vat", "termin", "płatność", "platnosc",
    "sprzedawca", "nabywca", "adres", "ulica", "ul", "al", "kod", "telefon", "email", "podpis",
    "wystawiono", "wystawiający", "wystawiajacy", "załącznik", "zalacznik", "nr", "numer",
    "pesel", "nip", "regon", "bank", "konto", "rachunek", "zapłacono", "zaplacono",
    "do", "od", "za", "na", "w", "we", "z", "ze", "i", "oraz", "the", "and", "a",
    "styczeń", "stycznia", "luty", "lutego", "marzec", "marca", "kwiecień", "kwietnia",
    "maj", "maja", "czerwiec", "czerwca", "lipiec", "lipca", "sierpień", "sierpnia",
    "wrzesień", "września", "pazdziernik", "październik", "października", "listopad",
    "listopada", "grudzień", "grudnia",
    "kopia", "oryginał", "oryginal", "duplikat", "paragon", "potwierdzenie", "przelew",
    "wpłata", "wplata", "zaliczka", "rabat", "opłata", "oplata", "suma",
    "miejsce", "miasto", "województwo", "wojewodztwo", "kraj", "polska", "polskie",
    "spółka", "spolka", "firma", "siedziba", "krs", "sąd", "sad", "regón", "wygenerowano",
    "dokument", "cena", "wartość", "wartosc", "ilość", "ilosc", "szt", "sztuk", "lp",
    "zleceniodawca", "zleceniobiorca", "zamieszkałą", "zamieszekala", "prowadzącym", "prowadzacym",
    "kontakt", "słownie", "slownie", "złotych", "zlotych", "groszy", "przedmiot", "umowy",
}

NAME_WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ](?:[a-ząćęłńóśźż]+|[A-ZĄĆĘŁŃÓŚŹŻ]+)(?:-[A-ZĄĆĘŁŃÓŚŹŻ](?:[a-ząćęłńóśźż]+|[A-ZĄĆĘŁŃÓŚŹŻ]+))*"
WORD_RE = re.compile(r"(?<!\w)" + NAME_WORD + r"(?!\w)")
LABEL_SPLIT_RE = re.compile(r"\s{2,}|;")

RE_MONEY   = re.compile(r"(?<![.\d])(?:\d{1,3}(?:[ \u00a0]\d{3})*|\d+)[.,]\d{2}\s?(?:zł|zl|PLN|EUR|USD|CHF|GBP|€|\$)")
RE_ACCOUNT = re.compile(r"(?<!\d)(\d{2}(?:[ \u00a0-]?\d{4}){6})(?!\d)")
RE_PESEL   = re.compile(r"(?<!\d)(\d{11})(?!\d)")
RE_NIP     = re.compile(r"(?<!\d)(\d{10})(?!\d)")
RE_POSTAL  = re.compile(r"(?<!\d)(\d{2}-\d{3})(?!\d)")
RE_GROSZ   = re.compile(r"\b\d{1,2}/100\b")   # grosze słownie: "00/100"
RE_PHONE   = re.compile(r"(?:\+\d{2}[ \-]?)?(?:\d[ \-]?){8,11}\d")
RE_PERCENT = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)\s?%(?!\d)")
RE_NUMGEN  = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,](\d{1,3}))?(?![\d.,])")
RE_MIXED = re.compile(r"(?<!\w)(?=[\w/-]*[^\W\d_])(?=[\w/-]*\d)[^\W_]+(?:[-/][^\W_]+)*(?!\w)", re.UNICODE)
RE_SYMBOL  = re.compile(r"(?<![A-Za-z\d/])([A-Z][A-Z0-9]{0,8}(?:[-/][A-Z0-9]{1,8}){1,5})(?![A-Za-z\d/])")

STREET_PREFIXES = ("ul.", "al.", "os.", "pl.", "ulica", "aleja", "aleje", "plac", "osiedle", "ul ", "al ")


def pesel_valid(p: str) -> bool:
    if len(p) != 11 or not p.isdigit():
        return False
    w = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    s = sum(int(d) * wi for d, wi in zip(p, w))
    return (10 - s % 10) % 10 == int(p[10])


def nip_valid(n: str) -> bool:
    if len(n) != 10 or not n.isdigit():
        return False
    w = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    s = sum(int(d) * wi for d, wi in zip(n, w))
    return s % 11 == int(n[9])


def _classify_number(label: str, token: str) -> tuple[str, float]:
    lab = label.lower()
    digits = re.sub(r"\D", "", token)
    if token.endswith("%"):
        return "procent", 0.8
    if "+" in token:
        return "telefon", 0.85
    if any(k in lab for k in ("zł", "pln", "eur", "usd", "kwot", "suma", "netto", "brutto", "cena", "rabat", "wartość", "wartosc", "opłat", "zapłat", "do zap")):
        if re.search(r"[.,]\d{2}", token) or "zł" in token:
            return "kwota", 0.9
    if len(digits) == 11 and digits.isdigit():
        if "pesel" in lab:
            return "PESEL", 0.98
        return ("PESEL", 0.85) if pesel_valid(digits) else ("numer", 0.35)
    if len(digits) == 10 and digits.isdigit():
        if "nip" in lab or "podatk" in lab:
            return "NIP", 0.97
        return ("NIP", 0.85) if nip_valid(digits) else ("numer", 0.35)
    if len(digits) in (9, 14) and digits.isdigit() and "regon" in lab:
        return "REGON", 0.95
    if len(digits) == 26 and digits.isdigit():
        return "nr konta", 0.95
    if "pesel" in lab and len(digits) == 11:
        return "PESEL", 0.98
    if "nip" in lab and len(digits) in (10, 13):
        return "NIP", 0.95
    if "regon" in lab and len(digits) in (9, 14):
        return "REGON", 0.95
    if any(k in lab for k in ("kont", "tel", "komórk", "komork", "faks", "mobil")):
        if 9 <= len(digits) <= 13:
            return "telefon", 0.9
    if any(k in lab for k in ("faktur", "rachunek", "numer", "nr", "paragon", "zamówien", "zamowien", "dowód", "dowod", "seria", "umow", "decyzj")):
        return "numer", 0.7
    stripped = token.strip()
    if re.match(r"^\d+([ \u00a0]\d{3})*[.,]\d{2}$", stripped):
        return "kwota?", 0.4
    if re.match(r"^\+?\d[\d\s-]{7,}$", stripped) and 9 <= len(digits) <= 13:
        return "telefon?", 0.45
    return "numer", 0.4


def _clean_label(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^[\s\-–—:;,•·]+|[\s\-–—:;,•·]+$", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def _label_for(row: dict, part_idx: int, match_start_in_line: int,
               rows: list, ri: int) -> str:
    """Etykieta w 3 krokach:
    (1) tekst na lewo w TEJ SAMEJ linii,
    (2) tekst na lewo w tym samym WIERZSZU (kolumna po lewej),
    (3) linia POWYŻEJ z pokryciem poziomym."""
    line = row["parts"][part_idx]
    text = line["text"]
    # (1)
    left = text[:match_start_in_line]
    parts_ = [p for p in LABEL_SPLIT_RE.split(left) if p.strip()]
    cand = _clean_label(parts_[-1]) if parts_ else ""
    if (cand.endswith(":") and len(cand) >= 2) or len(cand) >= 3:
        return cand
    if left.strip() and len(_clean_label(left)) >= 3:
        return _clean_label(left)
    # (2) — części wiersza na lewo, od najbliższej; sensowna gdy kończy się ':' lub jest krótka
    left_parts = [L for L in row["parts"] if L["bbox"][2] <= line["bbox"][0] + 1]
    name_like = re.compile(r"^[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:[ -][A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)+$")
    for L in reversed(left_parts[-3:]):
        t = _clean_label(L["text"])
        if not t:
            continue
        if name_like.match(t):
            continue  # po lewej jest kolejna nazwa/kolumna — to nie etykieta
        has_digit = any(ch.isdigit() for ch in t)
        if t.endswith(":") or (not has_digit and len(t.split()) <= 5 and len(t) >= 2):
            return t
        if not has_digit:
            return t[-60:]
    # (3) — linie powyżej z pokryciem poziomym
    x0, x1 = line["bbox"][0], line["bbox"][2]
    for j in range(ri - 1, max(-1, ri - 4), -1):
        for L in rows[j]["parts"]:
            ov = min(L["bbox"][2], x1) - max(L["bbox"][0], x0)
            if ov < -5:
                continue
            t = _clean_label(L["text"])
            if not t:
                continue
            if t.endswith((":", "=", "-")) or len(t.split()) <= 5:
                return t.rstrip(":=")[-60:]
    return cand or ""


# ------------------------------------------------------------------ linie ----
def extract_lines(page: "pymupdf.Page") -> list[dict]:
    font_xrefs = {}
    try:
        for xref, ext, ftype, basefont, refname, enc in page.get_fonts(full=False):
            font_xrefs[basefont] = xref
    except Exception:
        pass
    raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    lines = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for ln in block.get("lines", []):
            spans = []
            for sp in ln.get("spans", []):
                text = "".join(c["c"] for c in sp["chars"])
                spans.append(SpanInfo(text=text, bbox=tuple(sp["bbox"]), origin=tuple(sp["origin"]),
                                      font=sp["font"], size=sp["size"], color=sp["color"],
                                      flags=sp.get("flags", 0), xref=font_xrefs.get(sp["font"]),
                                      char_rects=[tuple(c["bbox"]) for c in sp["chars"]],
                                      char_origins=[tuple(c["origin"]) for c in sp["chars"]]))
            if not spans:
                continue
            lines.append({"text": "".join(s.text for s in spans), "bbox": tuple(ln["bbox"]),
                          "spans": spans, "dir": ln.get("dir", (1, 0))})
    lines.sort(key=lambda L: (round(L["bbox"][1], 1), L["bbox"][0]))
    return lines


def build_rows(lines: list[dict]) -> list[dict]:
    """Scala linie o zbliżonym Y w jeden wiersz logiczny (tekst + mapa pozycji)."""
    rows = []
    for L in lines:
        placed = False
        for R in rows:
            if abs(R["y0"] - L["bbox"][1]) <= 3.0 and R["dir"] == L["dir"]:
                R["parts"].append(L)
                placed = True
                break
        if not placed:
            rows.append({"y0": L["bbox"][1], "parts": [L], "dir": L["dir"]})
    out = []
    for R in rows:
        parts = sorted(R["parts"], key=lambda L: L["bbox"][0])
        text = ""
        cmap = []  # (pozycja_w_wierszu, indeks_czesci, pozycja_w_czesci)
        for pi, L in enumerate(parts):
            if text and not text.endswith(" ") and not L["text"].startswith(" "):
                # decyzja o separatorze: czy pionowa przerwa między częściami sugeruje spację?
                gap = L["bbox"][0] - parts[pi - 1]["bbox"][2] if pi else 0
                if gap > 0.6 * (parts[pi - 1]["spans"][0].size if parts[pi - 1]["spans"] else 10):
                    text += " "
            for ci in range(len(L["text"])):
                cmap.append((len(text) + ci, pi, ci))
            text += L["text"]
        bbox = [min(L["bbox"][0] for L in parts), min(L["bbox"][1] for L in parts),
                max(L["bbox"][2] for L in parts), max(L["bbox"][3] for L in parts)]
        out.append({"text": text, "bbox": tuple(bbox), "parts": parts, "cmap": cmap, "dir": R["dir"]})
    return out


def _row_to_line_pos(row: dict, start: int, end: int):
    """Zakres w wierszu -> [(indeks_czesci, s, e)], ograniczony do znaków z mapy."""
    ranges = {}
    for pos, pi, ci in row["cmap"]:
        if start <= pos < end:
            ranges.setdefault(pi, [ci, ci + 1])
            ranges[pi][0] = min(ranges[pi][0], ci)
            ranges[pi][1] = max(ranges[pi][1], ci + 1)
    return sorted(ranges.items())


def _sub_pieces(line: dict, start: int, end: int, resolver) -> list[Piece]:
    pieces = []
    g = 0
    for sp in line["spans"]:
        n = len(sp.text)
        s0, s1 = max(start - g, 0), min(end - g, n)
        g += n
        if s1 <= s0:
            continue
        frag = sp.text[s0:s1]
        if sp.char_rects:
            boxes = sp.char_rects[s0:s1]
            rect = (min(r[0] for r in boxes), min(r[1] for r in boxes),
                    max(r[2] for r in boxes), max(r[3] for r in boxes))
            origin = sp.char_origins[s0] if sp.char_origins else None
            pieces.append(Piece(span=sp, text=frag, rect=rect, origin=origin))
            continue
        fobj = resolver(sp)
        try:
            x_off = fobj.text_length(sp.text[:s0], fontsize=sp.size)
            w = fobj.text_length(frag, fontsize=sp.size)
        except Exception:
            total = max(sp.bbox[2] - sp.bbox[0], 0.1)
            x_off = total * s0 / n
            w = total * (s1 - s0) / n
        rect = (sp.bbox[0] + x_off, sp.bbox[1], sp.bbox[0] + x_off + w, sp.bbox[3])
        pieces.append(Piece(span=sp, text=frag, rect=rect))
    return pieces


def _row_pieces(row: dict, start: int, end: int, resolver) -> list[Piece]:
    pieces = []
    for pi, (s, e) in _row_to_line_pos(row, start, end):
        pieces.extend(_sub_pieces(row["parts"][pi], s, e, resolver))
    return pieces


def _classify_name(row_text: str, start: int, end: int, label: str) -> tuple[str, str, float]:
    before = row_text[:start].lower()
    lab_low = label.lower()
    if any(k in lab_low for k in NAME_LABELS):
        ttype = "nazwisko" if ("nazwisko" in lab_low and "imię" not in lab_low and "imie" not in lab_low) else "imię i nazwisko"
        return ttype, label, 0.9
    if any(k in before for k in NAME_LABELS):
        return "imię i nazwisko", _clean_label(before[-40:]) or label, 0.8
    seq = WORD_RE.findall(row_text[start:end])
    if len(seq) >= 2:
        return ("nazwisko" if len(seq) == 1 else "imię i nazwisko"), label, 0.55
    return "nazwa", label, 0.3


def _above_texts(rows, ri, x0=None, x1=None, max_up=3) -> list[str]:
    out = []
    for j in range(ri - 1, max(-1, ri - 1 - max_up), -1):
        prev = rows[j]
        if x0 is not None and (min(prev["bbox"][2], x1 or 0) - max(prev["bbox"][0], x0)) < -5:
            continue
        out.append(prev["text"])
    return out


# ------------------------------------------------------------------ analiza --
def analyze_lines(lines: list[dict], resolver=None, page_no=0, ocr: bool = False) -> list[Item]:
    """Analiza na gotowych liniach (z extract_lines albo z OCR)."""
    if ocr:
        # syntetyczne 'spany' OCR mają font='Helvetica' — rozwiązywany przez resolver do helv
        resolver = resolver or (lambda sp: fontmod.resolve_font("Helvetica", 0)["font"])
    resolver = resolver or (lambda sp: fontmod.resolve_font(sp.font, sp.flags)["font"])
    lines = [dict(line, text=classes.normalize_text(line["text"])) for line in lines]
    rows = build_rows(lines)
    items: list[Item] = []
    taken: list[tuple[int, int, int, int]] = []  # (row_idx, part_idx, s, e)

    def is_taken(ri, s, e, pi=None):
        return any((pi is None or t[1] is None or pi == t[1]) and ri == t[0] and s < t[3] and t[2] < e for t in taken)

    def add(ri, line, s, e, typ, label, score, hit=None, pi=None):
        pieces = _sub_pieces(line, s, e, resolver)
        if not pieces or is_taken(ri, s, e, pi):
            return
        taken.append((ri, pi, s, e))
        if ocr:
            score = min(score, 0.6)  # OCR — mniejsza pewność
        items.append(Item(id=uuid.uuid4().hex[:10], type=typ, value=line["text"][s:e],
                          label=label, page=page_no, pieces=pieces, date_hit=hit, score=score,
                          source="ocr" if ocr else "text", direction=tuple(line.get("dir", (1, 0)))))

    for ri, row in enumerate(rows):
        for pi, line in enumerate(row["parts"]):
            text = line["text"]

            def lab(ms, _pi=pi, _ri=ri):
                return _label_for(row, _pi, ms, rows, _ri)

            # Specific full values first, so letters/digits are not split up.
            for rx, typ in ((classes.EMAIL, "email"), (classes.URL, "adres www")):
                for m in rx.finditer(text):
                    end = m.end()
                    while end > m.start() and text[end - 1] in ".,;!?)":
                        end -= 1
                    add(ri, line, m.start(), end, typ, lab(m.start()), .95, pi=pi)

            # A city immediately following a postal code, including ALL CAPS.
            for m in RE_POSTAL.finditer(text):
                city = classes.CITY.match(text, m.end())
                if city:
                    add(ri, line, city.start(1), city.end(1), "miejscowość", "Miejscowość", .9, pi=pi)

            # Street + house number form one editable value. Without "ul." we
            # require address context (e.g. the postal-code line underneath).
            address_context = classes.postal_below(line, lines, RE_POSTAL)
            for m in classes.STREET.finditer(text):
                value = m.group()
                if (classes.STREET_PREFIX.match(value) or address_context
                        or re.search(r"(?i)adres\s*:\s*$", text[:m.start()])):
                    add(ri, line, m.start(), m.end(), "adres", "Adres", .9, pi=pi)

            if classes.COMPANY.search(text.strip()) and len(text) < 180:
                start = text.find(":") + 1 if ":" in text else 0
                while start < len(text) and text[start].isspace():
                    start += 1
                add(ri, line, start, len(text.rstrip()), "nazwa firmy", lab(start), .85, pi=pi)

            # Previously discarded fractions must remain editable too.
            for m in RE_GROSZ.finditer(text):
                add(ri, line, m.start(), m.end(), "ułamek", lab(m.start()), .9, pi=pi)

            # Alphanumeric identifiers are indivisible, including lower-case letters.
            for m in RE_MIXED.finditer(text):
                token = m.group()
                labelled = re.match(r"(?i)^(PESEL|NIP|REGON|telefon|tel)(?=\d)", token)
                unit = re.fullmatch(r"\d+(?:zł|zl|PLN|EUR|USD|CHF|GBP|kg|cm|mm|m)", token, re.I)
                if not labelled and not unit:
                    add(ri, line, m.start(), m.end(), "symbol", lab(m.start()), 0.8, pi=pi)

            # ---- 1) daty
            for hit in find_dates(text):
                add(ri, line, hit.start, hit.end, "data", lab(hit.start),
                    0.95 if hit.kind in ("dmy", "ymd") else 0.85, hit=hit, pi=pi)

            # ---- 2) konta, PESEL, NIP, kody pocztowe
            for rx, typ in ((RE_ACCOUNT, "nr konta"), (RE_PESEL, "PESEL"),
                            (RE_NIP, "NIP"), (RE_POSTAL, "kod pocztowy")):
                for m in rx.finditer(text):
                    if is_taken(ri, m.start(), m.end(), pi):
                        continue
                    label = lab(m.start())
                    low = label.lower()
                    dig = re.sub(r"\D", "", m.group(0))
                    if typ == "NIP" and "nip" not in low and not nip_valid(dig):
                        continue
                    if typ == "PESEL" and "pesel" not in low and not pesel_valid(dig):
                        continue
                    sc = 0.95
                    if typ == "kod pocztowy":
                        ctx = (label + " " + text[:m.start()]).lower()
                        if not any(k in ctx for k in ("kod", "poczt", "ul", "al", "adres", "mieszka")):
                            sc = 0.5
                    add(ri, line, m.start(), m.end(), typ, label, sc, pi=pi)

            # ---- 3) kwoty i numery ogólne
            for rx in (RE_MONEY, RE_SYMBOL, RE_PERCENT, RE_PHONE, RE_NUMGEN):
                for m in rx.finditer(text):
                    token = m.group(0)
                    if not token.strip() or is_taken(ri, m.start(), m.end(), pi):
                        continue
                    if rx is RE_PHONE and len(re.sub(r"\D", "", token)) < 9:
                        continue
                    label = lab(m.start())
                    typ, sc = _classify_number(label, token)
                    if rx is RE_MONEY:
                        typ, sc = "kwota", max(sc, 0.7)
                    if rx is RE_SYMBOL:
                        typ, sc = ("numer", 0.75) if any(k in label.lower() for k in ("nr", "numer", "faktur", "dowód", "dowod", "seria")) else ("symbol", 0.4)
                    if typ == "numer" and any(label.lower().startswith(p) for p in STREET_PREFIXES):
                        typ, sc = "ulica nr", 0.25
                    add(ri, line, m.start(), m.end(), typ, label, sc, pi=pi)

            # ---- 4) imiona i nazwiska
            for m in WORD_RE.finditer(text):
                word = m.group(0)
                s_, e_ = m.span()
                if word.lower() in STOPWORDS or text[e_:e_+1] == ":":
                    continue
                if is_taken(ri, s_, e_, pi):
                    continue
                rest = text[e_:]
                mm = re.match(r"((?:[ \t\u00a0]+" + NAME_WORD + r"){1,2})(?!\w)", rest)
                ext_end = e_
                if mm:
                    cand_end = e_ + mm.end(1)
                    candidate_words = WORD_RE.findall(text[s_:cand_end])
                    if (not any(w.lower() in STOPWORDS for w in candidate_words)
                            and not is_taken(ri, s_, cand_end, pi) and len(word) > 2):
                        ext_end = cand_end
                word_full = text[s_:ext_end]
                if word_full.lower() in STOPWORDS or len(word_full) < 3:
                    continue
                ttype, label, sc = _classify_name(text, s_, ext_end, lab(s_))
                if ttype == "nazwa" and len(re.findall(r"[A-ZĄĆĘŁŃÓŚŹŻ]", word_full)) < 2:
                    continue
                add(ri, line, s_, ext_end, ttype, label, sc, pi=pi)

            # Completeness pass: include every remaining non-whitespace range.
            # Intervals partition the original line; no duplicate/overlapping
            # editable values are introduced by the generic fallback.
            intervals = sorted((a, b) for r, part, a, b in taken if r == ri and part == pi)
            cursor = 0
            for start, end in intervals + [(len(text), len(text))]:
                left, right = cursor, start
                while left < right and text[left].isspace():
                    left += 1
                while right > left and text[right - 1].isspace():
                    right -= 1
                if left < right:
                    # Keep an unknown field label separate from its body too.
                    colon = text.find(":", left, right)
                    if left < colon < min(right - 1, left + 60) and any(c.isalpha() for c in text[left:colon]):
                        add(ri, line, left, colon + 1, "etykieta", "Etykieta pola", .85, pi=pi)
                        left = colon + 1
                        while left < right and text[left].isspace():
                            left += 1
                    typ, score = classes.fallback_type(text[left:right], line)
                    add(ri, line, left, right, typ, lab(left), score, pi=pi)
                cursor = max(cursor, end)

    items.sort(key=lambda it: (it.page, round(it.rect[1], 1), it.rect[0]))
    return items


def analyze_page(page, resolver=None, page_no=0, ocr: bool = False) -> list[Item]:
    return analyze_lines(extract_lines(page), resolver, page_no, ocr=ocr)


def analyze_document(path: str, progress=None):
    doc = pymupdf.open(path)
    if doc.needs_pass:
        doc.close()
        raise ValueError("PDF jest zabezpieczony hasłem. Otwórz niezabezpieczoną kopię.")
    if not doc.is_pdf or not doc.page_count:
        doc.close()
        raise ValueError("Plik nie jest poprawnym dokumentem PDF.")
    try:
        resolver = lambda sp: fontmod.resolve_font(sp.font, sp.flags)["font"]
        all_items = []
        pages_without_text = []
        for i, page in enumerate(doc):
            if not page.get_text("text").strip():
                pages_without_text.append(i)
                continue
            all_items.extend(analyze_page(page, resolver, page_no=i))
            if progress:
                progress(i + 1, doc.page_count)
        return all_items, pages_without_text
    finally:
        doc.close()
