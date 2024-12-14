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

@echo off

cd C:/Users/marca/Server/Logistics/Software/rclone

echo OFFICIAL RCLONE SYNC
echo GOAT-PC-2 SYNCED TO DROPBOX BUSINESS ADVANCED

echo -------------------------------------------
echo Sync [PUSH] Server-System-GOATPC2
"C:\Users\marca\Server\Logistics\Software\rclone\rclone.exe" sync --progress --bwlimit 5M --copy-links "C:/Users/marca/Server/Local/Server-System-GOATPC2" "Server-System-GOATPC2:"
echo -------------------------------------------

pause