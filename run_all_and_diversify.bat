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

python large_universe.py
python large_score.py