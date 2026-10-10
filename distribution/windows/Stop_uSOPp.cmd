@echo off
echo Finish active validations and exports before stopping uSOPp.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0usopp-local.ps1" stop
if errorlevel 1 pause
