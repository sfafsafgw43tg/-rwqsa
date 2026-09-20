# 🦎 KAMELEON PDF

**Profesjonalna, w pełni offline'owa aplikacja do czytania i podmiany danych w dokumentach PDF** — imion i nazwisk, wszystkich numerów (z ich opisami/etykietami) oraz dat — z zachowaniem oryginalnej czcionki, koloru i położenia, **bez nakładania elementów na siebie**.

---

## ✨ Możliwości

| Funkcja | Opis |
|---|---|
| 🔎 **Automatyczna analiza** | Wykrywa: daty (numeryczne i polskie słowne), imiona i nazwiska, kwoty, PESEL (z sumą kontrolną), NIP (z sumą kontrolną), REGON, numery kont bankowych, kody pocztowe, telefony, procenty, numery faktur/umów/dowodów — każdy element **z etykietą ("za co odpowiada")** pobraną z dokumentu |
| ✍️ **Podmiana 1:1** | Nowy tekst dostaje czcionkę oryginału (osadzoną w PDF lub najbliższy systemowy odpowiednik: Arial, Times, Courier, Calibri, Segoe UI…), ten sam kolor i pozycję |
| 📏 **Zero nakładania** | Gdy nowy tekst jest dłuższy — aplikacja mierzy wolną przestrzeń i albo rozszerza zapis w pustkę, albo automatycznie zmniejsza czcionkę tak, by zmieścić się w starym obrysie |
| 🗓 **Daty pod kontrolą** | Zmiana daty z zachowaniem formatu (`15.01.2024` → `10.03.2026`, `15 stycznia 2024 r.` → `10 marca 2026 r.`, `2024-01-15` → `2026-03-10`) + **zmiana dat pliku** (utworzony/zmodyfikowany, także data utworzenia na Windows) i **metadanych PDF** (CreationDate/ModDate) |
| 🖨 **OCR skanów** | Strony zeskanowane (bez warstwy tekstu) są rozpoznawane przez Tesseract (język polski), z pikselowym czyszczeniem starego tekstu przed wstawieniem nowego |
| 📚 **Tryb wsadowy** | To samo mapowanie zmian stosowane do wielu podobnych plików (np. faktur z jednego szablonu) — dopasowanie po etykiecie lub wartości, pobranie wszystkich wyników jako ZIP |
| 👁 **Podgląd na żywo** | Render strony przed/po zmianach z kolorowymi ramkami wykrytych danych |
| 📤 **Eksporty** | Zestawienie CSV/JSON (strona, typ, opis, wartość, czcionka, status), mapowanie JSON do trybu wsadowego |
| 🔒 **100% offline** | Wszystko działa lokalnie; żaden plik nie opuszcza komputera |

## 🚀 Instalacja (Windows)

1. Zainstaluj dwuklikiem **`instalator.bat`** — sam doinstaluje:
   - Pythona (przez `winget`, jeśli go nie ma),
   - biblioteki: `PyMuPDF`, `Flask`, `Pillow`, `pytesseract`,
   - opcjonalnie **Tesseract OCR** z polskim językiem (do skanów),
   - skrót „Kameleon PDF” na pulpicie.
2. Uruchom **`uruchom.bat`** — otwierze się przeglądarka z aplikacją (serwer działa lokalnie).

> Wymagania: Windows 10/11. Internet potrzebny tylko przy instalacji narzędzi.

## 🖱 Użycie

1. Przeciągnij PDF do okna (albo kliknij i wybierz plik).
2. Po prawej zobaczysz listę wykrytych danych z opisami — wpisz nowe wartości.
3. Kliknij **„✨ Zastosuj zmiany”**, obejrzyj podgląd wyniku i pobierz plik `*_ZMIENIONY.pdf`.
4. Panel **„🗓 Daty pliku”** zmieni daty systemowe pliku i metadane PDF.
5. Przycisk **„📚 Tryb wsadowy”**: zapisz mapowanie (przycisk `MAPA`), wgraj wiele plików, uruchom.

## 🧠 Jak działa silnik podmiany

1. Z oryginalnego fragmentu pobierane są pełne metadane: czcionka, rozmiar, kolor, punkt bazowy.
2. Próba ponownego użycia **czcionki osadzonej w PDF** (identyczny wygląd liter).
3. W przeciwnym razie dobierany jest najlepszy odpowiednik systemowy (Arial↔Liberation Sans, Times↔Liberation Serif itd.), a awaryjnie wbudowane fonty base-14.
4. Tło pod tekstem jest **próbkowane pikselowo** (mediana), więc podmiana wygląda naturalnie na każdym tle.
5. Stary tekst jest usuwany redakcją PDF (dla skanów: wymazywany z obrazu), nowy wstawiany w tym samym punkcie bazowym.
6. Szerokość nowego tekstu jest mierzona; przekroczenie obrysu = automatyczne zmniejszenie czcionki (poniżej progu użyteczności) lub rozszerzenie w wolną przestrzeń — **elementy nigdy na siebie nie nachodzą**.

## 📁 Struktura projektu

```
KameleonPDF/
├── instalator.bat          ← instalacja wszystkich składników (Windows)
├── uruchom.bat             ← start aplikacji (Windows)
├── uruchom.py              ← start aplikacji (Linux/macOS: python3 uruchom.py)
├── requirements.txt
├── app/
│   ├── webapp.py           ← serwer + API
│   ├── core/
│   │   ├── analyzer.py     ← wykrywanie imion, numerów, dat + etykiety
│   │   ├── replacer.py     ← podmiana z zachowaniem czcionki (redakcja+wstawienie)
│   │   ├── fonts.py        ← dopasowanie czcionek systemowych/osadzonych
│   │   ├── dates.py        ← parsowanie/formatowanie dat po polsku
│   │   ├── filedates.py    ← daty pliku i metadanych PDF
│   │   ├── batch.py        ← tryb wsadowy
│   │   ├── report.py       ← eksporty CSV/JSON/mapowanie
│   │   └── ocr.py          ← OCR + pikselowa rafinacja prostokątów
│   ├── templates/index.html
│   └── static/ (style.css, app.js)
├── przyklady/              ← przykładowe dokumenty do testów
└── tests/                  ← testy + generatory przykładów
```

## 🔒 Prywatność

Aplikacja nie ma żadnego połączenia z internetem w czasie pracy — serwer nasłuchuje wyłącznie lokalnie (`127.0.0.1`), a pliki pozostają na dysku użytkownika.

## ⚠️ Ograniczenia techniczne (uczciwie)

- PDF-y **zaszyfrowane hasłem** nie są obsługiwane.
- Podmiana działa na **warstwie tekstowej**; w skanach z bardzo złej jakości OCR warto zweryfikować wynik podglądem.
- Bardzo ozdobne/nietypowe fonty komercyjne są zastępowane najbliższym odpowiednikiem (rdzeń dokumentu pozostaje nietknięty).
- Tekst obrócony (nie poziomy) jest pomijany dla bezpieczeństwa układu.
