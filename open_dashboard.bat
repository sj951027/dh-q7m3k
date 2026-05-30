@echo off
cd /d "%~dp0"
if exist "docs\index.html" (
    start "" "docs\index.html"
) else (
    echo 아직 docs\index.html이 없습니다. run_screener.bat을 먼저 실행하세요.
    pause
)
