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

:: Add to Windows Startup via Scheduled Task
echo 🔧 Windows başlangıcına ekleniyor...
set TASK_NAME=CANAVAR_Agent
set SCRIPT_PATH=%~dp0agent.py

:: Delete old task if exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create new task: runs at logon
schtasks /create /tn "%TASK_NAME%" /tr "pythonw \"%SCRIPT_PATH%\"" /sc onlogon /rl highest /f >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Başlangıca eklendi! PC açıldığında otomatik çalışacak.
) else (
    echo ⚠️ Başlangıca eklenemedi. Yönetici olarak çalıştırmayı deneyin.
)
echo.

:: Start agent
echo 🚀 Agent başlatılıyor...
echo.
python "%~dp0agent.py"
pause
