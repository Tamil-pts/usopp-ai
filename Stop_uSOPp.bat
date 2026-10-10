@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_usopp.ps1" %*
if errorlevel 1 pause
