@echo off
setlocal

echo Launching Logistics...

REM Silently install UV if missing
winget list --id=astral-sh.uv --accept-source-agreements --accept-package-agreements | findstr /C:"astral-sh.uv" >nul
IF ERRORLEVEL 1 (
echo Installing UV...
winget install --id=astral-sh.uv -e --version 0.9.3 --silent --accept-source-agreements --accept-package-agreements
)

REM Set work dir
cd /d "%~dp0Python"

set "VIRTUAL_ENV=%~dp0venv"
uv run --active launch.py

endlocal
pause
