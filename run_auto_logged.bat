@echo off
rem [2026-08-11] AUTO wrapper: writes full log (stdout+stderr) to logs\auto_run_*.log
rem Point Task Scheduler at THIS file. No external redirection needed anymore.
rem Original run_all_and_diversify.bat is untouched.
cd /d "%~dp0"
if not exist logs mkdir logs
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set TS=%%i
set AUTO=1
rem [2026-09-11] daytime guard: if Task Scheduler fires a missed run after 09:00
rem (PC was off at 20:10 and "run ASAP after missed start" is on), intraday prices
rem would be stamped with today run_id. Allowed window: 20:00-23:59 or 00:00-08:59.
set HH=20
for /f %%h in ('powershell -NoProfile -Command "(Get-Date).Hour"') do set HH=%%h
if %HH% GEQ 9 if %HH% LSS 20 (
  >"logs\auto_run_%TS%_SKIPPED.log" echo [daytime_guard] hour=%HH% is outside 20:00-08:59 window - run skipped. %DATE% %TIME%
  exit /b 0
)
rem [2026-08-17] skip_once: one-shot skip for market holidays. If skip_once.flag
rem exists, write a marker log, delete the flag, exit 0. Next run is normal.
if exist skip_once.flag (
  >"logs\auto_run_%TS%_SKIPPED.log" echo [skip_once] flag found - run skipped, flag deleted. %DATE% %TIME%
  del skip_once.flag
  exit /b 0
)
call run_all_and_diversify.bat >> "logs\auto_run_%TS%.log" 2>&1
exit /b %ERRORLEVEL%
