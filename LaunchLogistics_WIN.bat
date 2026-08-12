:: BatchGotAdmin
:-------------------------------------
REM  --> Check for permissions
>nul 2>&1 %SYSTEMROOT%\system32\cacls.exe %SYSTEMROOT%\system32\config\system

REM --> If error flag set, we do not have admin.
if '%errorlevel%' NEQ '0' (
    echo Requesting administrative privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > %temp%\getadmin.vbs
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> %temp%\getadmin.vbs

    %temp%\getadmin.vbs
    exit /B

:gotAdmin
    if exist %temp%\getadmin.vbs ( del %temp%\getadmin.vbs )
    pushd %CD%
    CD /D %~dp0

:: Script to Launch Logistics
@echo off
:: mode con: cols=160 lines=50

set "VENV_PATH=%USERPROFILE%\Server\Logistics-VENV"

:: Create Server folder if needed
if not exist "%USERPROFILE%\Server" (
    echo Creating Server folder...
    mkdir "%USERPROFILE%\Server"
)

echo Initiating Logistics

echo Detecting Python 3.12.2 installation...
IF not exist "%LOCALAPPDATA%\Programs\Python\Python312" (GOTO setup_python)
echo Python 3.12.2 Detected! Proceeding...
GOTO :setup_venv

:setup_python
echo Installing Python 3.12.2(x64) ...
"%~dp0Software\python-3.12.2-amd64.exe" /quiet PrependPath=1 Include_test=0 SimpleInstall=1
echo Installed Python!
GOTO :setup_venv

:setup_venv
IF exist "%VENV_PATH%" (GOTO logistics_launch_script)
"%LOCALAPPDATA%\Programs\Python\Python312\python" -m venv "%VENV_PATH%"
GOTO :logistics_launch_script

:logistics_launch_script
call "%VENV_PATH%\Scripts\activate"
"%VENV_PATH%\Scripts\python" -m pip install -r "%~dp0Python\requirements.txt"
echo Executing Logistics...
"%VENV_PATH%\Scripts\python" "%~dp0Python\launch.py"
pause