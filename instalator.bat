@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title KAMELEON PDF — Instalator (100%% offline)
cls
echo.
echo  ============================================================
echo    KAMELEON PDF — INSTALATOR
echo    Profesjonalna zamiana danych w PDF (imiona, numery, daty)
echo    Ten instalator wymaga internetu TYLKO do pobrania narzędzi.
echo    sama APLIKACJA dziala pozniej w 100%% offline.
echo  ============================================================
echo.

cd /d "%~dp0"

:: ---------- 1. Sprawdzenie Pythona ----------
echo  [1/5] Sprawdzanie Pythona...
set "PYEXE="
python --version >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE py --version >nul 2>&1 && set "PYEXE=py"
if defined PYEXE (
    for /f "tokens=*" %%i in ('%PYEXE% --version 2^>^&1') do echo        znaleziono: %%i
    goto :have_python
)
echo        Nie znaleziono Pythona. Probujem zainstalowac przez winget...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo  NIE UDALO SIE ZAINSTALOWAC PYTHONA AUTOMATYCZNIE.
    echo  Pobierz recznie: https://www.python.org/downloads/
    echo  WAZNE: zaznacz przy instalacji "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
:: odswiezenie PATH po instalacji
set "PYEXE=py"
echo        Python zainstalowany.
:have_python
echo.

:: ---------- 2. Biblioteki Pythona ----------
echo  [2/5] Instalacja bibliotek (PyMuPDF, Flask, Pillow, pytesseract)...
%PYEXE% -m pip install --upgrade pip --quiet
%PYEXE% -m pip install -r requirements.txt
if errorlevel 1 (
    echo  Blad instalacji bibliotek. Sprawdz polaczenie z internetem i uruchom ponownie.
    pause
    exit /b 1
)
echo        Biblioteki OK.
echo.

:: ---------- 3. Tesseract OCR (opcjonalne, dla zeskanowanych PDF) ----------
echo  [3/5] Tesseract OCR (do zeskanowanych dokumentow)...
set "TESS_OK=0"
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS_OK=1"
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "TESS_OK=1"
if "!TESS_OK!"=="1" (
    echo        Tesseract juz zainstalowany — pomijam.
) else (
    set /p "INSTALL_TESS=       Zainstalowac Tesseract OCR? [T/n]: "
    if /i not "!INSTALL_TESS!"=="n" (
        winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
        if errorlevel 1 (
            echo        Winget nie zadzialal — probuje pobrac instalator bezposrednio...
            powershell -Command "try { Invoke-WebRequest -Uri 'https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe' -OutFile '$env:TEMP\tesseract_setup.exe'; Start-Process \"$env:TEMP\tesseract_setup.exe\" /S -Wait } catch { exit 1 }"
            if errorlevel 1 (
                echo        Nie udalo sie. OCR mozna doinstalowac pozniej.
            ) else (
                echo        Tesseract zainstalowany.
            )
        ) else (
            echo        Tesseract zainstalowany.
        )
    )
)
echo.

:: ---------- 4. Weryfikacja ----------
echo  [4/5] Weryfikacja instalacji...
%PYEXE% -c "import pymupdf, flask, PIL; print('       PyMuPDF', pymupdf.__version__.split(':')[1] if ':' in pymupdf.__version__ else 'OK', '| Flask OK | Pillow OK')" 2>nul
if errorlevel 1 (
    echo  Weryfikacja NIEPOWODZENIE — uruchom instalator ponownie.
    pause
    exit /b 1
)
echo        Wszystko gotowe!
echo.

:: ---------- 5. Skroty ----------
echo  [5/5] Tworzenie skrotu na pulpicie...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Kameleon PDF.lnk'); $s.TargetPath = '%~dp0uruchom.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%SystemRoot%\System32\SHELL32.dll,220'; $s.Save()" 2>nul
echo        Skrot "Kameleon PDF" na pulpicie.
echo.
echo  ============================================================
echo    INSTALACJA ZAKONCZONA!
echo    Uruchom aplikacje plikiem:  uruchom.bat
echo  ============================================================
echo.
pause
