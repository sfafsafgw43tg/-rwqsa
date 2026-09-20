# PrOximAl <small>edit</small>

Lokalna aplikacja **komputerowa** do podmiany danych w PDF. Natywne okno Qt,
prosty ciemnoszary interfejs, polskie opisy. **Nie otwiera przeglądarki,
nie uruchamia serwera HTTP i nie wymaga internetu podczas pracy.**

## Windows — instalacja i uruchomienie

Wymagania: Windows 10/11, 64-bitowy Python 3.10+ (zalecany 3.12).

1. Umieść projekt w stałym folderze, do którego masz prawo zapisu.
2. Uruchom `instalator.bat`. Instalacja pobiera biblioteki do osobnego `.venv`;
   jeśli nie ma Pythona, próbuje zainstalować go przez `winget`.
3. Instalator automatycznie tworzy **skrót „PrOximAl” na pulpicie**, wskazujący
   na `pythonw.exe` i aplikację. Nie trzeba zostawiać otwartego terminala.
4. Uruchom skrót lub `uruchom.bat`. Otworzy się okno **PrOximAl edit**.

Internet jest potrzebny **przy instalacji**, nie do edytowania dokumentów.
Przeniesienie folderu aplikacji wymaga ponownego utworzenia skrótu.

### Własna ikona

W tej wersji repozytorium **nie było załączonych `csssanvas.png` ani `1.png`**.
Obecna ikona „P” jest wyłącznie zastępcza, nie odtworzeniem przesłanej grafiki.

Wstaw `csssanvas.png` (alternatywnie `1.png`) do folderu głównego projektu
lub `app/assets/`, a następnie uruchom instalator ponownie. Grafika zostanie
przekonwertowana do wielorozmiarowego `.ico` dla skrótu; aplikacja użyje również
własnej grafiki. Gdy oba pliki istnieją w jednym folderze, pierwszeństwo ma
`csssanvas.png`. Sam skrót i ikonę można odświeżyć poleceniem:

```bat
.venv\Scripts\python.exe -m app.shortcut
```

### OCR (opcjonalne)

Instalator oferuje Tesseract OCR. Do polskich skanów wymagany jest również
`pol.traineddata` w katalogu `tessdata` instalacji Tesseracta. Plik językowy
należy zainstalować z oficjalnego projektu Tesseract (`tesseract-ocr/tessdata`)
lub instalatora zawierającego polski pakiet. OCR wykrywa też typowy katalog
`C:\Program Files\Tesseract-OCR`, nawet jeśli nie ma go w PATH.
Brak OCR **nie blokuje edycji tekstowych PDF**. Brak języka jest zgłaszany w oknie.

## Ekran startowy i szablony PDF

Po uruchomieniu zobaczysz **Start / Szablony**: ciemny, prosty układ inspirowany
aplikacjami Adobe — panel boczny z akcjami i lista lokalnych dokumentów.
Nie wymaga konta, chmury ani przeglądarki.

- Wkładaj PDF-y do folderu **`templates/`** obok `uruchom.bat`. Podfoldery
  i rozszerzenie `.PDF` też są obsługiwane. Lista pojawia się od razu przy starcie.
- **Otwórz folder** otwiera lokalny menedżer plików. Po powrocie do okna
  aplikacji lista się odświeża; dostępny jest również przycisk **Odśwież**.
- **Dodaj szablony…** kopiuje wybrane pliki do biblioteki. Istniejące nazwy
  nie są nadpisywane: nowe kopie otrzymują `(2)`, `(3)` itd.
- Wyszukaj nazwę, zaznacz plik i wybierz **Użyj szablonu** lub kliknij dwukrotnie.
  Edytujesz kopię roboczą, nie plik wzoru.
- **Utwórz PDF…** (`Ctrl+N`) otwiera kreator: nazwa, A4/A5/Letter,
  pion/poziom, 1–100 stron oraz opcjonalny nagłówek i tekst pierwszej strony.
  PDF zostaje zapisany w bibliotece i otwarty do pracy. Puste pola tworzą pusty
  dokument. Jest to prosty kreator, a nie pełny edytor układu stron jak Acrobat;
  treść nie przepływa automatycznie na kolejne strony. Zbyt długi tekst zgłasza błąd.
- **Narzędzia → Zapisz jako szablon…** dodaje bieżący dokument do biblioteki.
  Jeśli zmieniono wartości, najpierw użyj „Zastosuj i sprawdź”.
- **Start / Szablony** (`Alt+Home`) nie zamyka dokumentu ani nie usuwa zmian.
  **Wróć do dokumentu** przywraca edytor. Wybór innego pliku nadal pyta
  o porzucenie niezapisanych zmian.

Własne PDF-y w `templates/` są ignorowane przez Git. Usuwanie i przenoszenie
szablonów odbywa się zwyczajnie w menedżerze plików. Szczegóły: `templates/README.md`.

## Użycie

1. **Otwórz PDF** (`Ctrl+O`) lub przeciągnij lokalny plik do okna.
2. Po lewej jest podgląd. Kliknięcie ramki wybiera wartość do edycji po prawej.
   Ramki i strona używają tej samej skali, również przy powiększaniu i obrocie strony.
3. W tabeli edytuj kolumnę **Nowa wartość** albo użyj:
   - **Losuj zaznaczone** — jeden lub kilka wierszy (`Ctrl+klik`),
   - **Losuj widoczne** — tylko wiersze zgodne z filtrem i zakresem stron.
     Odznacz „Tylko bieżąca strona”, aby uwzględnić cały dokument.
4. **Zastosuj i sprawdź** generuje wynik z niezmienionej kopii źródła.
   Przełączaj „Pokaż wynik”, aby porównać. Na wyniku ramki oryginału są celowo
   ukryte: zmieniony tekst może mieć inną szerokość.
5. **Zapisz PDF jako…** (`Ctrl+Shift+S`) zapisuje oddzielny plik na dysku.
   Oryginału nie można nadpisać. Po kolejnej edycji trzeba ponownie zastosować zmiany.

**Cofnij / Ponów** (`Ctrl+Z` / `Ctrl+Y`) obejmuje ręczne wpisy, import mapowania,
losowanie i wyczyszczenie zmian. Kliknięcie „Wyczyść zmiany” też można cofnąć.
Powiększenie: `+`, `−`, `Ctrl+kółko myszy`; „Dopasuj” przywraca dopasowanie strony.

### Narzędzia

- Opcje podmiany: minimalny rozmiar pisma, wykorzystanie wolnego miejsca,
  czcionki osadzone i wypełnienie tła.
- Daty zapisywanego pliku: metadane PDF i czas modyfikacji; systemowa data
  utworzenia jest obsługiwana na Windows. Ustawienia dotyczą **eksportu**,
  nigdy źródłowego pliku. Aby zapisać samą zmianę dat, można zastosować dokument
  bez zmian tekstu, a następnie zapisać kopię.
- Eksport CSV/JSON, zapis i wczytywanie mapowania zmian.
- Tryb wsadowy: mapowanie + wiele plików + folder wyników. Istniejące wyniki
  nie są nadpisywane — dodawany jest licznik w nazwie. Dopasowanie po starej
  wartości ma pierwszeństwo przed etykietą, aby nie zmieniać innej kwoty
  tylko dlatego, że ma podobny opis.
- Raport ostatnich podmian: pokazuje zmniejszenie pisma i pominięte wartości.

## Losowanie i bezpieczeństwo danych

Losowanie odbywa się lokalnie, bez usług zewnętrznych. Obsługuje daty, osoby,
kwoty, numery i połączone identyfikatory, np. `AB12CD34`, `abc12DEF34`, `FV/2024/01/15`.
Zachowuje schemat liter/cyfr i separatorów w symbolach. PESEL ma poprawną datę
oraz sumę kontrolną; NIP, REGON i polski numer konta mają odpowiednie cyfry kontrolne.
W ramach jednej operacji jednakowe wartości są zastępowane jednakowo;
różne zapisy tej samej daty dostają spójną nową datę.

**To dane syntetyczne, nie gwarantowana anonimizacja.** Wygenerowany numer może
przypadkowo pokrywać się z rzeczywistym. Losowanie nie gwarantuje zachowania
zależności biznesowych (np. suma kwot, VAT, zgodność daty z PESEL).
Niewykryte dane, obrazy, załączniki, formularze i metadane mogą nadal zawierać
informacje poufne. Sprawdź cały dokument przed udostępnieniem.

Aplikacja pracuje na kopii w prywatnym katalogu tymczasowym `proximal-*`.
Katalog jest usuwany po zamknięciu dokumentu/aplikacji; po awarii procesu
może pozostać w systemowym katalogu plików tymczasowych. Nie jest to bezpieczne
wymazywanie danych z dysku. Stary folder `praca/` nie jest już używany.

## Ograniczenia

- Wykrywanie jest heurystyczne: nie każdy tekst zostanie wykryty jako dane.
- Zabezpieczone hasłem PDF-y są odrzucane z komunikatem.
- Tekst obrócony wewnątrz strony jest pomijany; obrót całej strony jest obsługiwany.
- OCR wymaga kontroli — pozycje znaków wewnątrz słów są przybliżone, a tekst
  na obrazie nie zachowa identycznej czcionki.
- Jeśli nowy tekst nie mieści się przy minimalnej czcionce, podmiana jest
  **pomijana**, a oryginał pozostaje. Sprawdź raport, zwłaszcza po losowaniu.
- Nietypowe czcionki mogą wymagać zamiennika. Edycja unieważnia podpisy cyfrowe PDF.
- Nie jest to edytor pełnego układu dokumentu ani narzędzie do weryfikowania autentyczności.

## Linux / macOS

Wymagany jest lokalny pulpit graficzny i biblioteki systemowe Qt.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python uruchom.py
```

Na Debianie/Ubuntu typowe zależności to `libgl1`, `libegl1`, `libxkbcommon0`,
`libdbus-1-3`, `libxcb-cursor0`, `libxkbcommon-x11-0`, `libxcb-icccm4`,
`libxcb-keysyms1`, `libxcb-shape0`, `libxcb-xinerama0` i `libxcb-randr0`.
Skrót Windows nie jest tworzony na tych platformach.

## Testy i struktura

```sh
python -m pip install pytest
python tests/test_suite.py
python -m pytest -q
```

Wyniki i granice weryfikacji: [TESTY.md](TESTY.md).
Testy Qt używają `QT_QPA_PLATFORM=offscreen`, ale nadal potrzebują systemowych
bibliotek graficznych. Workflow `.github/workflows/tests.yml` przewiduje
Linux i Windows; jego dodanie nie oznacza, że został już wykonany w GitHub Actions.

- `app/home.py` — ekran startowy, wybór szablonu i kreator PDF;
- `app/core/templates.py` — lokalna biblioteka i tworzenie/import szablonów;
- `app/desktop.py` — natywne okno, tabela, podgląd i operacje w tle;
- `app/core/document.py` — kopia robocza, cofanie, wynik i bezpieczny eksport;
- `app/core/analyzer.py` — wykrywanie i rzeczywista geometria znaków;
- `app/core/randomize.py` — losowanie danych lokalnie;
- pozostałe `app/core/` — podmiana, czcionki, daty, OCR, mapowania, raporty;
- `app/shortcut.py` — konwersja PNG do ICO i skrót Windows;
- `app/webapp.py` — wyłącznie kompatybilny alias do startu desktopowego, bez serwera.

Jeżeli start przez `pythonw` się nie powiedzie, szczegóły są w
`%LOCALAPPDATA%\PrOximAl\startup-error.log` (Windows) lub `~/PrOximAl/` (Linux/macOS).
