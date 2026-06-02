@echo off
chcp 65001 >nul
title Earth Zoom Bot
cd /d "%~dp0"

REM Один клик: системный прокси, venv, зависимости, запуск бота
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_bot.ps1"
if errorlevel 1 pause
