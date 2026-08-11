@echo off
rem [2026-08-11] MANUAL wrapper: writes full log (stdout+stderr) to logs\manual_run_*.log
rem Log is written to disk in real time - closing this window does NOT lose the log.
rem AUTO=1 below only suppresses inner pause/folder-open (interaction happens here instead).
cd /d "%~dp0"
if not exist logs mkdir logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set TS=%%i
set LOGF=logs\manual_run_%TS%.log
echo ============================================================
echo  Running screener... full log: %LOGF%
echo  Watch live in another window:
echo    powershell Get-Content %LOGF% -Wait -Tail 20
echo  (This window stays quiet until it finishes. Do not close
echo   unless you must - but even then, the log is safe on disk.)
echo ============================================================
set AUTO=1
call run_all_and_diversify.bat >> "%LOGF%" 2>&1
echo Done. Exit code %ERRORLEVEL%. Opening log...
start notepad "%LOGF%"
pause
