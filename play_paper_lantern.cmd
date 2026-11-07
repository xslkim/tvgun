@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0gunforge\start_game.ps1"
if errorlevel 1 pause
