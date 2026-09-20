# Przegląd i testy — 20.09.2026

## Przed edycją

Przejrzano wszystkie moduły aplikacji, interfejs JS/CSS/HTML, instalator,
launcher, instrukcje, generator przykładów oraz dotychczasowy zestaw testów.
Pierwsza próba uruchomienia wykazała brak PyMuPDF w środowisku. Po instalacji
zależności wykonano testy **na oryginalnym kodzie**:

- `python tests/test_suite.py`: **30 zaliczonych, 0 nieudanych**.
- Rzeczywisty OCR: pominięty, brak Tesseracta.

Dodatkowe próby oryginalnego kodu:

- `Numer: AB12CD34` — identyfikator nie był wykrywany.
- `Numer: 123456` — ramka miała X od ok. 84,41 do 126,40,
  podczas gdy tekst znajdował się od ok. 79,12 do 115,81.
- `fit_size` zwracał 4 pt dla tekstu o szerokości 266,8 pt,
  mimo dostępnych zaledwie 20 pt: ryzyko nakładania było realne.
- W rezerwacji `00/100` znaleziono trzyczęściowy wpis w strukturze,
  której pozostały kod używał jako czteroczęściowej. Zależnie od wiersza
  skutkowało to fałszywą detekcją albo błędem indeksowania.
- Serwer uruchamiał przeglądarkę i nasłuchiwał na `0.0.0.0`,
  mimo opisu sugerującego wyłącznie interfejs lokalny.

## Zmiany architektury i naprawy

1. Qt Widgets zamiast przeglądarki, Flask i endpointów upload/download.
   Żaden serwer nie jest już uruchamiany. Operacje używają lokalnych plików.
2. Geometria `rawdict/chars` zamiast pomiarów fontem zastępczym.
   PDF i ramki w tych samych jednostkach, obrót strony uwzględniony.
3. Dane alfanumeryczne, krótkie numery, połączone etykiety/cyfry,
   daty w wielu kolumnach i rezerwacja groszy.
4. Pomijanie tekstu przekraczającego dostępną szerokość; poprawka trybu
   „bez wypełnienia”; poprawne flagi czcionek osadzonych.
5. Cofanie i ponawianie, losowanie, reset, zabezpieczenie przed zapisem
   nieaktualnego wyniku, prywatna kopia robocza i atomowy zapis eksportu.
6. Ścisłe dopasowanie wartości przy mapowaniu wsadowym, zamiast zmieniania
   niezwiązanych danych tylko z powodu wspólnej etykiety.
7. Poprawka 64-bitowych sygnatur Windows HANDLE i stref czasowych dat.
   Metadane XMP niezwiązane z datami nie są zastępowane nowym pustym opisem.
8. OCR: wykrywanie typowej instalacji Windows, kontrola języka,
   zachowanie słownej geometrii zamiast nieograniczonego rozszerzania ramek.
9. Instalator z osobnym venv, pythonw, generatorem ICO i skrótem na pulpicie.

## Weryfikacja po zmianach

Środowisko: Linux, Python 3.11.2, PyMuPDF 1.28.2.

- Dotychczasowy zestaw: **30 zaliczonych, 0 nieudanych**.
- `python -m pytest -q`: **38 zaliczonych, 1 pominięty moduł**.
- `python -m compileall -q app uruchom.py`: zakończone poprawnie.
- `git diff --check`: brak błędów whitespace.
- Ruff (`--select F`) dla nowych modułów i testów: brak błędów.

Nowe testy sprawdzają m.in. wykrywanie identyfikatorów mieszanych i różnych
spanów, dokładność ramek w czterech obrotach strony, zachowanie sąsiadujących
tekstów, zbyt długie podmiany, sumy kontrolne danych losowych, spójne daty,
cofanie i ponawianie, brak starych zmian po resecie, ochronę oryginału,
czyszczenie kopii roboczej, szyfrowane/błędne PDF, metadane XMP,
czas eksportu, geometrię OCR z kontrolowanymi danymi i użycie dostarczonego PNG.

## Czego nie potwierdzono w tym środowisku

- **Natywnego okna Qt nie udało się uruchomić**: brak systemowych bibliotek
  `libGL.so.1`, `libEGL.so.1`, `libxkbcommon.so.0`, `libdbus-1.so.3`.
  Próba doinstalowania ich przez apt była zablokowana przez dostęp sieciowy
  środowiska. Moduł testów GUI jest jawnie pomijany, nie liczony jako sukces.
- Testy GUI obejmujące okno, klikanie/wybór danych, obrót, skalę, filtry,
  losowanie, cofanie, podmianę w tle i eksport są dodane w `tests/test_desktop.py`.
- **Instalatora BAT, skrótu Windows i Windows SetFileTime nie uruchomiono na
  systemie Windows.** Konwersja dostarczonego PNG do ICO została przetestowana
  niezależnie od Windows.
- Rzeczywistego Tesseract OCR nie wykonano. Testy z kontrolowanymi wynikami
  rozpoznawania nie zastępują próby na skanach.
- Workflow Linux/Windows dodano do GitHub Actions, ale **nie uruchamiano go**.
- Plików `csssanvas.png` i `1.png` nie było w repozytorium ani załącznikach;
  nie można potwierdzić zgodności zastępczej grafiki z oczekiwaną ikoną.

## Krótka lista kontroli na Windows

1. Instalator w ścieżce zawierającej spacje/polskie litery, utworzenie skrótu.
2. Start skrótem: własne okno PrOximAl, bez przeglądarki i terminala.
3. Faktura i umowa z `przyklady/`: kliknięcie ramek, zoom, filtry i edycja.
4. PDF wielostronicowy/obrócony: zgodność ramek i danych na kolejnych stronach.
5. Losowanie zaznaczenia i całego dokumentu; cofnij/ponów, reset i ponowna podmiana.
6. Za długi tekst: raport pominięcia; oryginał i sąsiedni tekst nieuszkodzone.
7. Eksport do nowej nazwy, ponowne otwarcie, daty pliku i metadane.
8. Opcjonalnie OCR polskiego skanu oraz wsad wielu plików.
9. Zamknięcie z niezapisanymi zmianami i podczas pracy w tle.

## Rozszerzenie: biblioteka szablonów i ekran startowy

Przed tą zmianą ponownie wykonano: **30 testów dotychczasowego zestawu**
i **38 testów pytest**, bez niepowodzeń; moduł GUI nadal pominięty.

Po dodaniu biblioteki `templates/`, ekranu Start i kreatora:

- `python -m pytest -q`: **61 zaliczonych, 1 pominięty moduł GUI**.
- Dotychczasowy zestaw: **30 zaliczonych**.
- Kompilacja modułów, Ruff (`--select F`) dla zmienionych modułów/testów
  oraz `git diff --check`: bez błędów.

23 nowe przypadki testowe sprawdzają tworzenie folderu, A4/A5/Letter w obu
orientacjach, wielostronicowe PDF-y, polskie znaki, dosłowny tekst HTML,
kontrolę przepełnienia strony, bezpieczne nazwy Windows, kolizje nazw,
import, podfoldery, ręczne dodawanie/usuwanie plików, ochronę wzoru podczas
edycji kopii, błędne formaty/opcje i zaszyfrowane dokumenty.

Dodano także testy Qt dotyczące startu aplikacji w bibliotece, wyszukiwania,
wyboru szablonu, powrotu do dokumentu i ustawień kreatora. **Nie zostały tutaj
wykonane**, z tej samej przyczyny co wcześniejsze testy GUI (brak bibliotek Qt
w systemie). Na Windows należy dodatkowo sprawdzić odświeżanie listy po powrocie
z Eksploratora oraz otwieranie folderu przyciskiem.
