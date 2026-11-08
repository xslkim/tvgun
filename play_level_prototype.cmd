@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0gunforge\start_level_player.ps1" %*
if errorlevel 1 pause
