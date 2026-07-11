@echo off
title V2.6 Screener + Diversify
chcp 65001 > nul

cd /d "%~dp0"

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
    pause
    exit /b %EXIT_CODE%
)

echo.
echo ========================================================================
echo   [Large] universe + buyback + observe + flows + report (approx 8 min)
echo ========================================================================
python large_universe.py
python catalyst_large.py
python large_score.py
python kis_flows.py --universe all --sleep 0.1 --flows-db ..\dh-q7m3k-data\ohlcv.db

echo.
echo ========================================================================
echo   [Large] build report (daily_ohlcv already updated above)
echo ========================================================================
python build_large_report.py

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
echo Opening result folder...
start "" "%~dp0"
echo.
echo Press any key to close this window.
pause > nul

