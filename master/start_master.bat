@echo off
chcp 65001 >nul 2>&1
title CANAVAR Monitor - Master Server
color 0A

echo ══════════════════════════════════════════════════════
echo   🐾 CANAVAR Monitor - Master Server Başlatılıyor
echo ══════════════════════════════════════════════════════
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python bulunamadı! Python kurulu olmalıdır.
    echo    https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install dependencies
echo 📦 Gerekli paketler kontrol ediliyor...
pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
echo ✅ Paketler hazır!
echo.

:: Open browser
echo 🌐 Tarayıcı açılıyor...
start "" "http://localhost:5000"

:: Start server
echo 🚀 Master sunucu başlatılıyor...
echo.
python "%~dp0app.py"
pause
