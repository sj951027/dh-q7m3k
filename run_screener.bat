@echo off
title V2.6 Screener

cd /d "%~dp0"

for /f "delims=" %%T in ('powershell -NoProfile -Command "(Get-Date).ToString('o')"') do set START_ISO=%%T
set START_TIME=%TIME%

echo.
echo ========================================================================
echo   V2.6 KOSPI / KOSDAQ Screener (Local Run)
echo ========================================================================
echo   Start: %DATE% %START_TIME%
echo ========================================================================
echo.

if "%DART_API_KEY%"=="" (
    echo [ERROR] DART_API_KEY environment variable is not set.
    echo Please check SETUP_LOCAL.md Step 3 and open a new terminal.
    echo.
    pause
    exit /b 1
)

echo [OK] DART API key detected
echo.
echo Pipeline starting. Takes about 60-120 minutes.
echo Please do not close this window.
echo.

python run_all_v2_6.py

set EXIT_CODE=%ERRORLEVEL%
set END_TIME=%TIME%

for /f "delims=" %%T in ('powershell -NoProfile -Command "$s=[datetime]::Parse('%START_ISO%'); $d=(Get-Date)-$s; if ($d.TotalHours -ge 1) { '{0}h {1}m {2}s' -f [int]$d.Hours, [int]$d.Minutes, [int]$d.Seconds } else { '{0}m {1}s' -f [int]$d.Minutes, [int]$d.Seconds }"') do set ELAPSED=%%T

if %EXIT_CODE% NEQ 0 (
    echo.
    echo ========================================================================
    echo   [FAIL] Error occurred during execution
    echo ========================================================================
    echo   Start: %START_TIME%
    echo   End:   %END_TIME%
    echo   Total elapsed: %ELAPSED%
    echo ========================================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================================
echo   [OK] Pipeline completed successfully
echo ========================================================================
echo   Start: %START_TIME%
echo   End:   %END_TIME%
echo   ** Total elapsed: %ELAPSED% **
echo ========================================================================
echo.
echo Output files:
echo   - latest_kospi_final.csv
echo   - latest_kosdaq_final.csv
echo.
echo Opening result folder...
echo.

start "" "%~dp0"

echo Press any key to close this window.
pause > nul