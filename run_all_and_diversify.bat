@echo off
title V2.6 Screener + Diversify
chcp 65001 > nul
rem [2026-07-26] UTF-8 강제: 스케줄러(AUTO)로 로그 리다이렉트 시 cp949 인코딩으로
rem 이모지 출력이 UnicodeEncodeError 로 죽는 것 방지. 수동 실행에도 무해.
set PYTHONUTF8=1

cd /d "%~dp0"

rem [2026-08-22] weekday-intraday guard: block Mon-Fri 09:00-15:59 runs.
rem Intraday prices contaminate observation data (2026-08-21 incident).
rem Early morning (<09h) and weekend daytime stay allowed. Override: set FORCE_RUN=1
rem Fail-open design: sentinel defaults keep the run allowed if powershell fails.
set GUARD_DOW=9
set GUARD_HH=99
if not defined FORCE_RUN (
  for /f %%w in ('powershell -NoProfile -Command "[int](Get-Date).DayOfWeek"') do set GUARD_DOW=%%w
  for /f %%h in ('powershell -NoProfile -Command "(Get-Date).Hour"') do set GUARD_HH=%%h
)
set GUARD_BLOCK=0
if %GUARD_DOW% GEQ 1 if %GUARD_DOW% LEQ 5 if %GUARD_HH% GEQ 9 if %GUARD_HH% LEQ 15 set GUARD_BLOCK=1
if %GUARD_BLOCK% EQU 1 (
  echo [guard] Blocked: weekday intraday run - dow=%GUARD_DOW% hour=%GUARD_HH%.
  echo [guard] Market-hours prices contaminate observation data - see patch_note/20260821_intraday_run_cleanup.md
  echo [guard] Run after market close, or:  set FORCE_RUN=1  then re-run.
  exit /b 0
)

echo.
echo ========================================================================
echo   V2.6 Screener + Sector Diversify (Local Run)
echo ========================================================================
echo   Start: %DATE% %TIME%
echo ========================================================================
echo.
echo This runs the full screener and then the sector-diversified picks.
echo It can take 60-120 minutes. Please do not close this window.
echo.

set SCREENER_NO_SNAPSHOTS=1

echo.
echo ========================================================================
echo   [B track] daily_ohlcv FIRST (Phase2: screener reuses ohlcv prices)
echo   universe_ohlcv before screener - ensures ohlcv latest date == today
echo ========================================================================
python universe_ohlcv.py

echo.
echo ========================================================================
echo   [B track] market series + universe events (P2/P3 data layers, non-fatal)
echo ========================================================================
python market_series.py
python universe_events.py

python run_and_diversify.py

set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% NEQ 0 (
    echo.
    echo ========================================================================
    echo   [FAIL] Something went wrong (exit code %EXIT_CODE%^)
    echo   Check the messages above. If it mentions DART_API_KEY,
    echo   set up your .env file (see .env.example^) and try again.
    echo ========================================================================
    echo.
    if not defined AUTO pause
    exit /b %EXIT_CODE%
)

echo.
echo ========================================================================
echo   [Large] universe + buyback + observe + flows + report (approx 8 min)
echo ========================================================================
python large_universe.py
python catalyst_large.py
python large_score.py
python kis_flows.py --universe all --sleep 0.1 --flows-db ..\dh-q7m3k-data\ohlcv.db --with-credit --with-loan
python fetch_consensus.py

echo.
echo ========================================================================
echo   [Large] build report (daily_ohlcv already updated above)
echo ========================================================================
python build_large_report.py
python build_large_test.py

echo.
echo ========================================================================
echo   [Large] Push docs/_large_obs.html to GitHub (Pages auto-deploy)
echo ========================================================================
python -c "import run_and_diversify as r; r.git_push()"

echo.
echo ========================================================================
echo   [Cleanup] rotate old outputs + weekly DB backup (7d guard inside)
echo ========================================================================
python cleanup.py --yes --backup-db

echo.
echo ========================================================================
echo   [OK] Done.  End: %DATE% %TIME%
echo ========================================================================
echo   Output:
echo     - latest_kospi_final.csv / latest_kosdaq_final.csv
echo     - diversified_picks_*.csv
echo ========================================================================
echo.
if not defined AUTO (
  echo Opening result folder...
  start "" "%~dp0"
  echo.
  echo Press any key to close this window.
  pause > nul
)

