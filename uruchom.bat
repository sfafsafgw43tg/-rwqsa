@echo off
chcp 65001 >nul
title KAMELEON PDF
cd /d "%~dp0"

set "PYEXE="
python --version >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE py --version >nul 2>&1 && set "PYEXE=py"

if not defined PYEXE (
    echo Nie znaleziono Pythona. Uruchom najpierw: instalator.bat
    pause
    exit /b 1
)

%PYEXE% -c "import pymupdf" 2>nul || (
    echo Biblioteki nie sa zainstalowane. Uruchom najpierw: instalator.bat
    pause
    exit /b 1
)

echo Uruchamianie KAMELEON PDF... (okno mozna zminimalizowac, nie zamykac)
%PYEXE% uruchom.py
if errorlevel 1 (
    echo.
    echo Aplikacja zakonczyla sie bledem. Skontaktuj sie z supportem / sprawdz logi wyzej.
    pause
)
