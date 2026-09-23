@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%launch_config.ini"

if not exist "%CONFIG_FILE%" (
    echo ERROR: launch_config.ini was not found next to this launcher.
    echo   Expected: %CONFIG_FILE%
    call :Pause
    exit /b 1
)

for %%F in ("%CONFIG_FILE%") do if %%~zF EQU 0 (
    echo ERROR: launch_config.ini is empty.
    echo   %CONFIG_FILE%
    call :Pause
    exit /b 1
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo ERROR: Windows PowerShell was not found.
    echo This launcher requires Windows PowerShell to read launch_config.ini and bootstrap uv.
    call :Pause
    exit /b 1
)

call :ReadLaunchConfig commonutils_root COMMONUTILS_ROOT_VALUE
if errorlevel 1 (
    call :Pause
    exit /b 1
)

if not defined COMMONUTILS_ROOT_VALUE (
    echo ERROR: commonutils_root is missing or empty in [Launch] in:
    echo   %CONFIG_FILE%
    call :Pause
    exit /b 1
)

set "COMMONUTILS_ROOT_VALUE=%COMMONUTILS_ROOT_VALUE:/=\%"

if "%COMMONUTILS_ROOT_VALUE:~1,1%"==":" (
    echo ERROR: commonutils_root must be relative to the project launcher directory.
    echo   Value: %COMMONUTILS_ROOT_VALUE%
    call :Pause
    exit /b 1
)
if "%COMMONUTILS_ROOT_VALUE:~0,1%"=="\" (
    echo ERROR: commonutils_root must be relative to the project launcher directory.
    echo   Value: %COMMONUTILS_ROOT_VALUE%
    call :Pause
    exit /b 1
)

for %%I in ("%SCRIPT_DIR%%COMMONUTILS_ROOT_VALUE%") do set "COMMONUTILS_ROOT=%%~fI"
set "COMMON_LAUNCHER=%COMMONUTILS_ROOT%\launchers\LaunchPythonProject_WIN.bat"

if not exist "%COMMONUTILS_ROOT%\." (
    echo ERROR: Configured commonUtils root does not exist or is not a directory:
    echo   %COMMONUTILS_ROOT%
    call :Pause
    exit /b 1
)

if not exist "%COMMON_LAUNCHER%" (
    echo ERROR: Shared Windows launcher was not found:
    echo   %COMMON_LAUNCHER%
    call :Pause
    exit /b 1
)

call "%COMMON_LAUNCHER%" "%SCRIPT_DIR%" "%CONFIG_FILE%"
set "LAUNCH_STATUS=%ERRORLEVEL%"
exit /b %LAUNCH_STATUS%

:ReadLaunchConfig
set "CONFIG_KEY=%~1"
set "CONFIG_OUTPUT=%TEMP%\commonutils_launch_%RANDOM%_%RANDOM%.tmp"
if exist "%CONFIG_OUTPUT%" del /q "%CONFIG_OUTPUT%" >nul 2>&1

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $path=$env:CONFIG_FILE; $key=$env:CONFIG_KEY; $inLaunch=$false; $values=New-Object System.Collections.Generic.List[string]; foreach($line in [IO.File]::ReadAllLines($path)){ $t=$line.Trim(); if($t -match '^\[(.+)\]$'){ $inLaunch=($matches[1].Trim() -ieq 'Launch'); continue }; if(-not $inLaunch -or $t.Length -eq 0 -or $t.StartsWith('#') -or $t.StartsWith(';')){ continue }; $idx=$line.IndexOf('='); if($idx -lt 0){ continue }; if($line.Substring(0,$idx).Trim() -ieq $key){ $v=$line.Substring($idx+1).Trim(); if($v.Length -ge 2){ if(($v[0] -eq [char]34 -and $v[$v.Length-1] -eq [char]34) -or ($v[0] -eq [char]39 -and $v[$v.Length-1] -eq [char]39)){ $v=$v.Substring(1,$v.Length-2) } }; $values.Add($v) } }; if($values.Count -gt 1){ [Console]::Error.WriteLine(('ERROR: Duplicate ''{0}'' entries were found in [Launch] in {1}.' -f $key,$path)); exit 2 }; if($values.Count -eq 1){ [IO.File]::WriteAllText($env:CONFIG_OUTPUT,$values[0]) } else { [IO.File]::WriteAllText($env:CONFIG_OUTPUT,'') }"
set "READ_STATUS=%ERRORLEVEL%"
if not "%READ_STATUS%"=="0" (
    if exist "%CONFIG_OUTPUT%" del /q "%CONFIG_OUTPUT%" >nul 2>&1
    echo ERROR: Failed to read '%~1' from launch_config.ini.
    exit /b %READ_STATUS%
)

set "%~2="
set /p "%~2="<"%CONFIG_OUTPUT%" 2>nul
if exist "%CONFIG_OUTPUT%" del /q "%CONFIG_OUTPUT%" >nul 2>&1
exit /b 0

:Pause
if not defined COMMONUTILS_NO_PAUSE pause
exit /b 0
