@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_usopp.ps1" -Lan %*
if errorlevel 1 pause
