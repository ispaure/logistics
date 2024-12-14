:: BatchGotAdmin
:-------------------------------------
REM  --> Check for permissions
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

REM --> If error flag set, we do not have admin.
if '%errorlevel%' NEQ '0' (
    echo Requesting administrative privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"

    "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%CD%"
    CD /D "%~dp0"

:: Script to Launch Marc's Server Logistics UI
@echo off
:: mode con: cols=160 lines=50

echo Initiating Marc's Server Logistics UI

echo Detecting Python installation...
IF not exist "%LOCALAPPDATA%\Programs\Python\Python310" (GOTO setup_python)
echo Python Detected! Proceeding...
GOTO :logistics_launch_script

:setup_python
echo Installing Python...
"%~dp0/Software/python-3.10.7-amd64.exe" /quiet PrependPath=1 Include_test=0 SimpleInstall=1
echo Installed Python!
GOTO :logistics_launch_script

:logistics_launch_script
pip install dirsync
pip install pySide2
echo Executing Marc's Server Logistics UI Script
python "%~dp0\Python\launch.py"
pause