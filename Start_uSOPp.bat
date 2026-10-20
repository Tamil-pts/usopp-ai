@echo off
setlocal
if /I "%~1"=="stop" goto stop
if /I "%~1"=="restart" goto restart
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_usopp.ps1" %*
goto finish
:stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_usopp.ps1" -Action Stop %2 %3 %4 %5 %6 %7 %8 %9
goto finish
:restart
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_usopp.ps1" -Action Restart %2 %3 %4 %5 %6 %7 %8 %9
:finish
set "USOPP_LAUNCH_EXIT=%ERRORLEVEL%"
if not "%USOPP_LAUNCH_EXIT%"=="0" pause
exit /b %USOPP_LAUNCH_EXIT%
