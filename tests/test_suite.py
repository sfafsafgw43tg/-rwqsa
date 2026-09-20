# -*- coding: utf-8 -*-
"""PrOximAl edit — pełny test regresyjny. Uruchom: python3 tests/test_suite.py"""
import sys, os, shutil, datetime as dt
import tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
_TEMP = tempfile.TemporaryDirectory(prefix="proximal-tests-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf
from app.core.classification import normalize_text
from app.core import analyzer, replacer, dates, filedates, fonts as fontmod
from app.core.replacer import ReplaceOptions

PASS, FAIL = [], []

def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  ({extra})" if extra else ""))

print("=" * 60)
print("TESTY PrOximAl edit")
print("=" * 60)

# ---------------------------------------------------------------- daty
print("\n[1] Silnik dat")
h = dates.find_dates("płatność do 15.03.2026 zgodnie z umową")[0]
check("data DD.MM.RRRR", h.text == "15.03.2026")
check("format zachowany", dates.format_same_style(h, dt.date(2027, 11, 5)) == "05.11.2027")
h2 = dates.find_dates("z dnia 3 kwietnia 2026 r.")[0]
check("data słowna", h2.text == "3 kwietnia 2026 r.")
check("słownie->słownie", dates.format_same_style(h2, dt.date(2027, 1, 28)) == "28 stycznia 2027 r.")
h3 = dates.find_dates("okres 2026-02-10")[0]
check("data ISO", h3.text == "2026-02-10" and dates.format_same_style(h3, dt.date(2025, 12, 31)) == "2025-12-31")
h4 = dates.find_dates("za miesiąc luty 2024")[0]
check("miesiąc+rok", h4.kind == "month-y" and dates.format_same_style(h4, dt.date(2024, 5, 1)) == "maj 2024")
h5 = dates.find_dates("data: 5.1.26")[0]
check("rok 2-cyfrowy", dates.format_same_style(h5, dt.date(2027, 12, 9)) == "9.12.27")

# ---------------------------------------------------------------- checksumy
print("\n[2] Walidatory numerów")
check("PESEL poprawny", analyzer.pesel_valid("44051401359"))
check("PESEL błędny", not analyzer.pesel_valid("44051401358"))
check("NIP poprawny", analyzer.nip_valid("5260001246"))
check("NIP błędny", not analyzer.nip_valid("5260001247"))

# ---------------------------------------------------------------- czcionki
print("\n[3] Silnik czcionek")
r = fontmod.resolve_font("Arial", 0)
check("Arial -> odpowiednik systemowy", r["source"] in ("system", "builtin"), r["font"].name)
r = fontmod.resolve_font("ABCDEF+TimesNewRomanPS-BoldMT", 0)
check("subset+bold rozpoznany", r["bold"] and r["family"] == "times", r["font"].name)
r = fontmod.resolve_font("Courier", 8)  # flaga mono z bitów
check("Courier -> mono", r["family"] == "courier")
s, shrunk = fontmod.fit_size(r["font"], "DŁUGI NOWY TEKST TESTOWY 12345", 10, 50)
check("fit_size zmniejsza", s < 10, f"{s:.2f}pt")

# ---------------------------------------------------------------- analiza
print("\n[4] Analiza dokumentów")
items_f, empty_f = analyzer.analyze_document("przyklady/przyklad_faktura.pdf")
types_f = {i.type for i in items_f}
check("faktura: daty", "data" in types_f)
check("faktura: osoby", any(t in types_f for t in ("imię i nazwisko", "nazwisko")))
check("faktura: kwoty", "kwota" in types_f)
check("faktura: PESEL+NIP+konto", {"PESEL", "NIP", "nr konta"} <= types_f)
lbl = next((i.label for i in items_f if i.value == "85010112345"), "")
check("etykieta PESEL", lbl == "PESEL", lbl)
lbl2 = next((i.label for i in items_f if i.value == "61 1090 1014 0000 0712 1981 2874"), "")
check("etykieta konta", lbl2 == "Numer konta", lbl2)
items_u, _ = analyzer.analyze_document("przyklady/przyklad_umowa.pdf")
check("umowa: TTF polskie znaki", any(i.value == "Katarzyna Zielińska" for i in items_u))

# ---------------------------------------------------------------- podmiana
print("\n[5] Silnik podmiany (bez nakładania)")
mapping = {"Jan Kowalski": "Piotr Zadrożny-Lewandowski", "15.01.2024": "10.03.2026",
           "15 stycznia 2024 r.": "10 marca 2026 r.", "85010112345": "92050567890",
           "7 921,20 zł": "15 999,99 zł", "61 1090 1014 0000 0712 1981 2874": "75 2490 0005 0000 4600 7430 1234",
           "FV/2024/01/15": "FV/2026/03/99-A"}
jobs = [(it, mapping[it.value]) for it in items_f if it.value in mapping]
reps = replacer.apply_replacements("przyklady/przyklad_faktura.pdf", os.path.join(_TEMP.name, "t_out.pdf"), jobs, ReplaceOptions())
check("wszystkie podmiany OK", all(r["status"].startswith("ok") for r in reps), f"{len(reps)} operacji")
doc = pymupdf.open(os.path.join(_TEMP.name, "t_out.pdf")); t = normalize_text(doc[0].get_text()); doc.close()
check("stare usunięte", not any(o in t for o in mapping))
check("nowe obecne", all(n in t for n in mapping.values()))
# geometrycznie: brak kolizji
items2, _ = analyzer.analyze_document(os.path.join(_TEMP.name, "t_out.pdf"))
col = 0
for a in items2:
    for b in items2:
        if a.id >= b.id: continue
        inter = pymupdf.Rect(a.rect) & pymupdf.Rect(b.rect)
        if not inter.is_empty and inter.get_area() > 0.35 * min(pymupdf.Rect(a.rect).get_area(), pymupdf.Rect(b.rect).get_area()):
            col += 1
check("geometrycznie brak nakładania", col == 0, f"kolizje: {col}")

# ---------------------------------------------------------------- daty pliku
print("\n[6] Daty pliku i metadane")
shutil.copy(os.path.join(_TEMP.name, "t_out.pdf"), os.path.join(_TEMP.name, "t_dates.pdf"))
filedates.set_file_times(os.path.join(_TEMP.name, "t_dates.pdf"), modified=dt.datetime(2024, 1, 5, 12, 0))
st = filedates.get_file_times(os.path.join(_TEMP.name, "t_dates.pdf"))
check("mtime zmienione", st["modified"].strftime("%Y%m%d%H") == "2024010512")
filedates.set_pdf_dates(os.path.join(_TEMP.name, "t_dates.pdf"), creation=dt.datetime(2019, 6, 1, 8, 30))
meta = filedates.get_pdf_metadata(os.path.join(_TEMP.name, "t_dates.pdf"))
check("PDF CreationDate", "2019" in (meta.get("creationDate") or ""), meta.get("creationDate", ""))

# ---------------------------------------------------------------- raporty
print("\n[7] Eksporty")
from app.core import report as report_mod
report_mod.export_report(os.path.join(_TEMP.name, "rep.csv"), items_f, reps)
check("CSV zapisany", os.path.getsize(os.path.join(_TEMP.name, "rep.csv")) > 500)
report_mod.export_mapping(os.path.join(_TEMP.name, "map.json"), items_f)
import json
check("mapowanie JSON", len(json.load(open(os.path.join(_TEMP.name, "map.json"), encoding="utf-8-sig"))) >= 0)

# ---------------------------------------------------------------- OCR (opcjonalny)
print("\n[8] OCR (jeśli Tesseract dostępny)")
from app.core import ocr as ocrmod
if ocrmod.tesseract_available():
    src = pymupdf.open("przyklady/przyklad_faktura.pdf")
    pix = src[0].get_pixmap(dpi=200)
    scan = pymupdf.open(); page = scan.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    import pytesseract
    lang = "pol" if "pol" in pytesseract.get_languages() else "eng"
    words = ocrmod.ocr_words_with_geometry(page, lang=lang)
    check("OCR słowa", len(words) > 40, f"{len(words)} słów")
    lines = [{"text": "PESEL: 85010112345 ", "bbox": (40, 160, 160, 175),
              "spans": [analyzer.SpanInfo("PESEL: 85010112345 ", (40, 160, 160, 175), (40, 172), "Helvetica", 10, 0, 0)],
              "dir": (1, 0)}]
    its = analyzer.analyze_lines(lines, page_no=0, ocr=True)
    check("analiza linii OCR", any(i.type == "PESEL" for i in its))
    scan.close(); src.close()
else:
    print("  (pominięto — brak Tesseract)")

print("\n" + "=" * 60)
print(f"WYNIK: {len(PASS)} zaliczonych, {len(FAIL)} nieudanych")
if FAIL:
    print("NIEUDANE:", FAIL)
    sys.exit(1)
print("WSZYSTKO OK ✅")
