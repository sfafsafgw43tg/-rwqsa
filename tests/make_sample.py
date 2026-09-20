# -*- coding: utf-8 -*-
"""Generator przykładowych dokumentów testowych dla KAMELEON PDF.
Używa prawdziwych fontów TTF (Liberation = odpowiednik Arial/Times/Courier),
aby polskie znaki działały jak w prawdziwych dokumentach."""
import os
import glob
import pymupdf

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "przyklady")
os.makedirs(OUT, exist_ok=True)


def _find_font(*patterns):
    for base in ("/usr/share/fonts", os.path.expanduser("~/.fonts"),
                 r"C:\Windows\Fonts"):
        for pat in patterns:
            hits = glob.glob(os.path.join(base, "**", pat), recursive=True)
            if hits:
                return hits[0]
    return None

SANS = _find_font("LiberationSans-Regular.ttf", "Arial.ttf", "DejaVuSans.ttf")
SANS_B = _find_font("LiberationSans-Bold.ttf", "Arialbd.ttf", "DejaVuSans-Bold.ttf")
SERIF = _find_font("LiberationSerif-Regular.ttf", "Times.ttf", "DejaVuSerif.ttf")
SERIF_B = _find_font("LiberationSerif-Bold.ttf", "Timesbd.ttf", "DejaVuSerif-Bold.ttf")
MONO = _find_font("LiberationMono-Regular.ttf", "cour.ttf", "DejaVuSansMono.ttf")

def _reg(page, alias, path):
    if path:
        page.insert_font(fontname=alias, fontfile=path)
        return alias
    return {"sans": "helv", "sansb": "hebo", "serif": "tiro", "serifb": "tibo", "mono": "cour"}[alias]


def sample_invoice(path: str):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    def t(x, y, s, size=10, font="sans", color=(0, 0, 0)):
        page.insert_text((x, y), s, fontsize=size, fontname=_reg(page, font, SANS), color=color)

    t(40, 50, "FAKTURA VAT", 22, "sansb", (0.1, 0.1, 0.3))
    t(400, 45, "Nr: FV/2024/01/15", 12, "sansb", (0.55, 0.08, 0.08))
    t(400, 62, "Data wystawienia: 15.01.2024", 10)
    t(400, 76, "Data sprzedaży: 15 stycznia 2024 r.", 10)
    page.draw_line(pymupdf.Point(40, 69), pymupdf.Point(555, 69), color=(0.1, 0.1, 0.3), width=1.2)

    t(40, 100, "Sprzedawca:", 11, "sansb")
    t(40, 116, "Jan Kowalski", 11)
    t(40, 130, "ul. Kwiatowa 13/4", 10)
    t(40, 144, "00-001 Warszawa", 10)
    t(40, 158, "NIP: 1234567890", 10)
    t(40, 172, "PESEL: 85010112345", 10)
    t(40, 186, "Telefon: +48 601 234 567", 10)

    t(320, 100, "Nabywca:", 11, "sansb")
    t(320, 116, "Anna Nowak-Kowalska", 11)
    t(320, 130, "al. Jerozolimskie 101", 10)
    t(320, 144, "02-011 Warszawa", 10)
    t(320, 158, "NIP: 9876543210", 10)

    page.draw_rect(pymupdf.Rect(40, 210, 555, 236), color=(0.1, 0.1, 0.3), fill=(0.92, 0.93, 0.98))
    t(48, 227, "Lp.", 10, "sansb"); t(80, 227, "Nazwa towaru", 10, "sansb")
    t(300, 227, "Ilość", 10, "sansb"); t(360, 227, "Cena netto", 10, "sansb"); t(470, 227, "Wartość", 10, "sansb")
    rows = [
        ("1", "Usługa projektowa strona internetowa", "1", "3 500,00 zł", "3 500,00 zł"),
        ("2", "Hosting roczny serwer business", "12", "45,00 zł", "540,00 zł"),
        ("3", "Konserwacja i wsparcie techniczne miesięczne", "3", "800,00 zł", "2 400,00 zł"),
    ]
    y = 252
    for r in rows:
        t(48, y, r[0]); t(80, y, r[1]); t(310, y, r[2]); t(360, y, r[3]); t(470, y, r[4])
        y += 18
    page.draw_line(pymupdf.Point(40, y - 6), pymupdf.Point(555, y - 6), color=(0.6, 0.6, 0.6), width=0.5)

    y += 6
    t(360, y, "Razem netto:", 10, "serif"); t(470, y, "6 440,00 zł", 10, "serif")
    y += 16
    t(360, y, "VAT 23%:", 10, "serif"); t(470, y, "1 481,20 zł", 10, "serif")
    y += 16
    t(360, y, "Do zapłaty:", 11, "sansb", (0.1, 0.1, 0.3)); t(470, y, "7 921,20 zł", 11, "sansb", (0.55, 0.08, 0.08))

    t(40, y + 24, "Termin płatności: 29.01.2024", 10, "sansb")
    t(40, y + 38, "Numer konta: 61 1090 1014 0000 0712 1981 2874", 10, "mono")
    t(40, y + 52, "Sposób płatności: przelew elektroniczny", 10)

    page.draw_line(pymupdf.Point(40, 800), pymupdf.Point(555, 800), color=(0.6, 0.6, 0.6), width=0.5)
    t(40, 815, "Wygenerowano: 2024-01-15 | Dokument nr 15/2024 | strona 1/1", 8, "mono", (0.35, 0.35, 0.35))
    t(60, 770, "...............................", 10)
    t(60, 783, "podpis sprzedawcy", 8, "mono", (0.35, 0.35, 0.35))

    doc.save(path, garbage=3, deflate=True)
    doc.close()


def sample_contract(path: str):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    def t(x, y, s, size=10.5, font="serif", color=(0, 0, 0)):
        page.insert_text((x, y), s, fontsize=size, fontname=_reg(page, font, SERIF), color=color)

    t(160, 60, "UMOWA ZLECENIE", 16, "sansb")
    t(60, 90, "zawarta w dniu 20 stycznia 2024 r. w Warszawie", 10.5)
    body = [
        ("pomiędzy:", "serifb", 10.5, (0, 0, 0)),
        ("Zleceniodawca: Marek Wiśniewski", "serifb", 10.5, (0, 0, 0)),
        ("prowadzącym działalność pod firmą Marek Wiśniewski „MW-Service”", "serif", 10.5, (0, 0, 0)),
        ("NIP: 5556667777, REGON: 123456789", "serif", 10.5, (0, 0, 0)),
        ("a", "serif", 10.5, (0, 0, 0)),
        ("Zleceniobiorca: Katarzyna Zielińska", "serifb", 10.5, (0, 0, 0)),
        ("zamieszkałą: ul. Lipowa 8/2, 31-002 Kraków", "serif", 10.5, (0, 0, 0)),
        ("PESEL: 92050567890, dowód osobisty: ABC 123456", "serif", 10.5, (0, 0, 0)),
    ]
    y = 118
    for s, f, sz, c in body:
        t(60, y, s, sz, f, c)
        y += 17
    y += 10
    par = ("§1. Przedmiot umowy",
           "Cena zlecenia: 4 200,00 zł brutto (słownie: cztery tysiące dwieście złotych 00/100).",
           "Zaliczka: 1 000,00 zł wypłacona w dniu 05.01.2024.",
           "Pozostałe 3 200,00 zł — płatność do 2024-02-10.",
           "Kontakt telefoniczny: 602 345 678, e-mail: mw-service@example.pl")
    for s in par:
        t(60, y, s, 10.5, "serif")
        y += 17
    y += 20
    t(60, y, "Data podpisu: 20.01.2024", 10.5, "serif")
    t(60, y + 30, "...............................", 10.5)
    t(60, y + 43, "Marek Wiśniewski", 9, "mono", (0.3, 0.3, 0.3))
    t(360, y + 30, "...............................", 10.5)
    t(360, y + 43, "Katarzyna Zielińska", 9, "mono", (0.3, 0.3, 0.3))
    doc.save(path, garbage=3, deflate=True)
    doc.close()


if __name__ == "__main__":
    p1 = os.path.join(OUT, "przyklad_faktura.pdf")
    p2 = os.path.join(OUT, "przyklad_umowa.pdf")
    sample_invoice(p1)
    sample_contract(p2)
    print("fonty:", SANS, "|", SERIF, "|", MONO)
    print("OK:", p1, p2)
