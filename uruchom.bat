@echo off
chcp 65001 >nul
setlocal
title PrOximAl edit
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Najpierw uruchom instalator.bat.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -c "import pymupdf; from PySide6.QtWidgets import QApplication" >nul 2>&1
if errorlevel 1 (
    echo Brak bibliotek. Uruchom ponownie instalator.bat.
    pause
    exit /b 1
)
start "PrOximAl edit" ".venv\Scripts\pythonw.exe" "%~dp0uruchom.py" %*
