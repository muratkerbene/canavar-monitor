@echo off
chcp 65001 >nul 2>&1
title CANAVAR Monitor - Agent
color 0B

echo ══════════════════════════════════════════════════════
echo   🐾 CANAVAR Monitor - Agent Başlatılıyor
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

:: Start agent
echo 🚀 Agent başlatılıyor ve başlangıca ekleniyor...
echo.

:: Start agent
echo 🚀 Agent başlatılıyor...
echo.
python "%~dp0agent.py"
pause
