# -*- coding: utf-8 -*-
"""
PrOximAl edit — silnik dat.
Parsuje daty (numeryczne i polskie słowne), zapamiętuje ich format
i potrafi wygenerować NOWĄ datę w DOKŁADNIE takim samym formacie.
Obsługuje synchronizację: jedna zmiana daty aktualizuje wszystkie
warianty tej samej daty w dokumencie (15.01.2024 / 15 stycznia 2024 r. / 2024-01-15).
"""
from __future__ import annotations

import re
import datetime as dt
from dataclasses import dataclass, field

MONTHS_NOM = {  # mianownik
    1: "styczeń", 2: "luty", 3: "marzec", 4: "kwiecień", 5: "maj", 6: "czerwiec",
    7: "lipiec", 8: "sierpień", 9: "wrzesień", 10: "październik", 11: "listopad", 12: "grudzień",
}
MONTHS_GEN = {  # dopełniacz (po dniu)
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia", 5: "maja", 6: "czerwca",
    7: "lipca", 8: "sierpnia", 9: "września", 10: "października", 11: "listopada", 12: "grudnia",
}
MONTHS_NOM_EN = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
                 7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}
_MONTH_LOOKUP = {}
for _m, _n in MONTHS_GEN.items():
    _MONTH_LOOKUP[_n.lower()] = _m
for _m, _n in MONTHS_NOM.items():
    _MONTH_LOOKUP[_n.lower()] = _m
for _m, _n in MONTHS_NOM_EN.items():
    _MONTH_LOOKUP[_n.lower()] = _m
    _MONTH_LOOKUP[_n[:3].lower()] = _m
# dodaj formy zadeklinowane spotykane w dokumentach
_EXTRA = {"styczniu": 1, "lutym": 2, "marcu": 3, "kwietniu": 4, "maju": 5, "czerwcu": 6,
          "lipcu": 7, "sierpniu": 8, "wrześniu": 9, "październiku": 10, "listopadzie": 11, "grudniu": 12}
_MONTH_LOOKUP.update(_EXTRA)

_MONTH_ALT = "|".join(sorted((re.escape(k) for k in _MONTH_LOOKUP), key=len, reverse=True))

# ------------------------------------------------------------------ wzorce ---
@dataclass
class DateHit:
    text: str                    # oryginalny fragment tekstu
    start: int                   # pozycja w linii
    end: int
    kind: str                    # 'dmy' | 'ymd' | 'd-month-y' | 'month-y' | 'y'
    year: int | None = None
    month: int | None = None
    day: int | None = None
    label: str = ""              # uzupełniane przez analizator

    @property
    def date(self):
        if self.year and self.month and self.day:
            try:
                return dt.date(self.year, self.month, self.day)
            except ValueError:
                return None
        return None

_PATTERNS = [
    # 2024-01-15 / 2024.01.15 / 2024/01/15
    ("ymd", re.compile(r"(?<![\d./-])(\d{4})([.\-/])(\d{1,2})\2(\d{1,2})(?![\d./-]\d)")),
    # 15.01.2024 | 15-01-2024 | 15/01/2024 | 15.01.24
    ("dmy", re.compile(r"(?<![\d./-])(\d{1,2})([.\-/])(\d{1,2})\2(\d{4}|\d{2})(?![\d./-]\d)")),
    # 15 stycznia 2024 (r.)  /  15 stycznia 2024
    ("d-month-y", re.compile(r"(?<!\w)(\d{1,2})\s+(" + _MONTH_ALT + r")\.?(?:\s+(\d{4}))?((?:\s+r\.?)?)(?!\w)", re.IGNORECASE)),
    # styczeń 2024 / stycznia 2024
    ("month-y", re.compile(r"(?<!\w)(" + _MONTH_ALT + r")\s+(\d{4})(?!\w)", re.IGNORECASE)),
]

_NUM_MONTH_ALIASES = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
                      7: 7, 8: 8, 9: 9, 10: 10, 11: 11, 12: 12}


def _norm2(y: int) -> int:
    return 2000 + y if y < 100 else y


def find_dates(text: str) -> list[DateHit]:
    hits: list[DateHit] = []
    taken: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(s < te and ts < e for ts, te in taken)

    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            s, e = m.span()
            if overlaps(s, e):
                continue
            h = DateHit(text=..., start=s, end=e, kind=kind)
            h.text = text[s:e]
            if kind == "ymd":
                h.year, h.month, h.day = int(m.group(1)), int(m.group(3)), int(m.group(4))
            elif kind == "dmy":
                h.day, h.month = int(m.group(1)), int(m.group(3))
                h.year = _norm2(int(m.group(4)))
            elif kind == "d-month-y":
                h.day = int(m.group(1))
                h.month = _MONTH_LOOKUP.get(m.group(2).lower())
                h.year = int(m.group(3)) if m.group(3) else None
            elif kind == "month-y":
                h.month = _MONTH_LOOKUP.get(m.group(1).lower())
                h.year = int(m.group(2))
            if h.month is None or (h.month and not (1 <= h.month <= 12)):
                continue
            if h.day is not None and not (1 <= h.day <= 31):
                continue
            if h.year and h.month and h.day and h.date is None:
                continue
            hits.append(h)
            taken.append((s, e))
    hits.sort(key=lambda h: h.start)
    return hits


# --------------------------------------------------------- formatowanie ----
def _detect_zero_pad(text: str, group: str) -> bool:
    return len(group) == 2 and group.startswith("0")


def format_same_style(hit: DateHit, new_date: dt.date) -> str:
    """Odtwarza dokładnie styl oryginalnego zapisu dla nowej daty."""
    old = hit.text
    if hit.kind in ("dmy", "ymd"):
        sep = "." if "." in old else ("-" if "-" in old else "/")
        if hit.kind == "ymd":
            m_s = f"{new_date.month:02d}" if re.search(r"\d{2}", old) else str(new_date.month)
            parts = [str(new_date.year), m_s, f"{new_date.day:02d}"]
            return sep.join(parts)
        # dmy: sprawdź czy dzień/miesiąc miały zero wiodące, rok 2-cyfrowy?
        day_m = re.match(r"(\d{1,2})", old)
        year_m = re.search(r"(\d{2,4})$", old)
        # zero wiodące: jeśli miesiąc lub dzień w oryginale miały "0" — formatuj oba z zerem
        month_m = re.search(rf"[\.\-/](0?\d{{1,2}})[\.\-/]", old)
        month_pad = bool(month_m and month_m.group(1).startswith("0"))
        day_pad = bool(day_m and day_m.group(1).startswith("0")) or month_pad
        y2 = bool(year_m and len(year_m.group(1)) == 2)
        d = f"{new_date.day:02d}" if day_pad else str(new_date.day)
        mo = f"{new_date.month:02d}" if month_pad else str(new_date.month)
        y = f"{new_date.year % 100:02d}" if y2 else str(new_date.year)
        return f"{d}{sep}{mo}{sep}{y}"
    if hit.kind == "d-month-y":
        month_word = None
        mm = re.search(_MONTH_ALT, old, re.IGNORECASE)
        if mm:
            month_word = mm.group(0)
        # zachowaj formę (dopełniacz/mianownik) na podstawie oryginału
        low = (month_word or "").lower()
        if low in {MONTHS_NOM[i].lower() for i in range(1, 13)} and not low.endswith("a") or low in _EXTRA:
            pass
        # heurystyka: po dniu zawsze dopełniacz; jeśli oryginał był mianownikiem (np. błędny), zachowaj rodzinę słowa
        if low in {v.lower() for v in MONTHS_NOM.values()}:
            word = MONTHS_NOM[new_date.month]
        else:
            word = MONTHS_GEN[new_date.month]
        suffix = " r." if re.search(r"r\.\s*$", old) else (" r" if re.search(r"r\s*$", old) else "")
        return f"{new_date.day} {word} {new_date.year}{suffix}"
    if hit.kind == "month-y":
        low_old = old.lower()
        # mianownik czy dopełniacz?
        if any(low_old.startswith(MONTHS_NOM[i].lower()) for i in range(1, 13)):
            word = MONTHS_NOM[new_date.month]
        else:
            word = MONTHS_GEN[new_date.month]
        return f"{word} {new_date.year}"
    return str(new_date)


def date_key(hit: DateHit):
    d = hit.date
    if d:
        return ("d", d.toordinal())
    if hit.month and hit.year:
        return ("m", hit.year, hit.month)
    if hit.year:
        return ("y", hit.year)
    return None
