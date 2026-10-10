@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PROJECT_ROOT=%~dp0"
set "CONFIG_FILE=%PROJECT_ROOT%launch_config.ini"
set "PAUSE_AFTER_COMPLETED=false"

if not exist "%CONFIG_FILE%" (
    echo ERROR: launch_config.ini was not found:
    echo   %CONFIG_FILE%
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do (
    if /i "%%A"=="commonutils_root " set "COMMONUTILS_ROOT=%%B"
    if /i "%%A"=="commonutils_root" set "COMMONUTILS_ROOT=%%B"
    if /i "%%A"=="pause_after_completed " set "PAUSE_AFTER_COMPLETED=%%B"
    if /i "%%A"=="pause_after_completed" set "PAUSE_AFTER_COMPLETED=%%B"
)

if not defined COMMONUTILS_ROOT (
    echo ERROR: commonutils_root was not found in launch_config.ini.
    pause
    exit /b 1
)

for /f "tokens=* delims= " %%A in ("%COMMONUTILS_ROOT%") do set "COMMONUTILS_ROOT=%%A"
for /f "tokens=* delims= " %%A in ("%PAUSE_AFTER_COMPLETED%") do set "PAUSE_AFTER_COMPLETED=%%A"

set "COMMONUTILS_ROOT=%COMMONUTILS_ROOT:/=\%"
set "LAUNCHER=%PROJECT_ROOT%%COMMONUTILS_ROOT%\launchers\LaunchPythonProject_WIN.bat"

if not exist "%LAUNCHER%" (
    echo ERROR: Shared Python launcher was not found:
    echo   %LAUNCHER%
    pause
    exit /b 1
)

set "LOGISTICS_ROOT=%PROJECT_ROOT%"
set "LOGISTICS_ALLY_ROOT="
set "ENVIRONMENT_ROOT=%PROJECT_ROOT%"
for %%I in ("%PROJECT_ROOT%..\ally-tools") do set "ALLY_ROOT=%%~fI"
if exist "%ALLY_ROOT%\." (
    if not exist "%ALLY_ROOT%\Python\pyproject.toml" goto :InvalidAlly
    if not exist "%ALLY_ROOT%\logistics_launch.ini" goto :InvalidAlly
    if not exist "%ALLY_ROOT%\Python\ally_feature\__init__.py" goto :InvalidAlly
    set "ENVIRONMENT_ROOT=%ALLY_ROOT%"
    set "CONFIG_FILE=%ALLY_ROOT%\logistics_launch.ini"
    echo Using private Ally environment.
)
call "%LAUNCHER%" "%ENVIRONMENT_ROOT%" "%CONFIG_FILE%" "%PAUSE_AFTER_COMPLETED%"
exit /b %ERRORLEVEL%

:InvalidAlly
echo ERROR: Sibling ally-tools is missing its dependency manifest, Logistics launch config, or feature package.
exit /b 1
