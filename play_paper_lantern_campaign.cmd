@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0gunforge\start_level_player.ps1" -Package paper.lantern_city_cast -Candidate %*
if errorlevel 1 pause
