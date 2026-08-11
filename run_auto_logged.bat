@echo off
rem [2026-08-11] AUTO wrapper: writes full log (stdout+stderr) to logs\auto_run_*.log
rem Point Task Scheduler at THIS file. No external redirection needed anymore.
rem Original run_all_and_diversify.bat is untouched.
cd /d "%~dp0"
if not exist logs mkdir logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set TS=%%i
set AUTO=1
call run_all_and_diversify.bat >> "logs\auto_run_%TS%.log" 2>&1
exit /b %ERRORLEVEL%
