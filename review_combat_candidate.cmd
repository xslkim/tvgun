@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0gunforge\start_level_review.ps1" -Package paper.assault -Candidate %*
if errorlevel 1 pause
