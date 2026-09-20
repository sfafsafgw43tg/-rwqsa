@echo off
chcp 65001 >nul
setlocal EnableExtensions
title PrOximAl edit - instalator
cd /d "%~dp0"
echo.
echo PrOximAl edit - aplikacja komputerowa, bez przegladarki.
echo Internet jest potrzebny do instalacji, nie do pracy.
echo.
set "PYEXE="
py -3.12 --version >nul 2>&1 && set "PYEXE=py -3.12"
if not defined PYEXE (
    python --version >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
    py --version >nul 2>&1 && set "PYEXE=py"
)
if defined PYEXE goto python_ready
echo Instalowanie Python 3.12...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto error
set "PYEXE=py -3.12"
%PYEXE% --version >nul 2>&1
if errorlevel 1 (
    echo Python zainstalowany. Zamknij okno i uruchom instalator ponownie.
    pause
    exit /b 1
)
:python_ready
%PYEXE% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo Wymagany Python 3.10 lub nowszy. Zalecany 3.12.
    goto error
)
echo [1/4] Osobne srodowisko aplikacji...
if not exist ".venv\Scripts\python.exe" %PYEXE% -m venv .venv
if errorlevel 1 goto error
echo [2/4] Biblioteki...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" -c "import pymupdf, PIL, pytesseract; from PySide6.QtWidgets import QApplication"
if errorlevel 1 goto error
echo [3/4] OCR - opcjonalnie...
choice /C TN /N /M "Zainstalowac Tesseract OCR do skanow? [T/N]: "
if errorlevel 2 goto shortcut
winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
if errorlevel 1 echo OCR nie zostal zainstalowany. Edycja tekstowych PDF nadal dziala.
echo Jezyk polski wymaga pol.traineddata w folderze tessdata Tesseracta.
:shortcut
echo [4/4] Ikona i skrot PrOximAl na pulpicie...
".venv\Scripts\python.exe" -m app.shortcut
if errorlevel 1 (
    echo Nie udalo sie utworzyc skrotu. Mozesz uzyc uruchom.bat.
    goto error
)
echo.
echo Gotowe. Uruchom PrOximAl ze skrotu lub pliku uruchom.bat.
echo Pliki csssanvas.png lub 1.png w folderze aplikacji nadpisuja ikone zastepcza.
pause
exit /b 0
:error
echo.
echo Instalacja nie zostala zakonczona. Sprawdz komunikat powyzej.
pause
exit /b 1
