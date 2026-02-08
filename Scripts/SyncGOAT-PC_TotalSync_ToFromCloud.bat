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

cd /d "B:\Yagi Dropbox\Marc-Andre Voyer\Software\GIT\logistics\Software\Windows\rclone"

echo OFFICIAL RCLONE SYNC
echo GOAT-PC SYNCED TO DROPBOX BUSINESS ADVANCED

REM echo -------------------------------------------
REM echo Sync [PUSH] Server-Lib-ComicRack
REM rclone sync --progress --bwlimit 100M --copy-links "C:/Users/marca/Server/Local/REM Server-Lib-ComicRack" "Server-Lib-ComicRack:"
REM echo -------------------------------------------

REM echo -------------------------------------------
REM echo Sync [PUSH] Server-Lib-Calibre
REM rclone sync --progress --bwlimit 100M --copy-links "C:/Users/marca/Server/Local/REM Server-Lib-Calibre" "Server-Lib-Calibre:"
REM echo -------------------------------------------

echo -------------------------------------------
echo Sync [PUSH] Server-Lib-ROM
rclone sync --progress --bwlimit 100M --copy-links "C:/Users/marca/Server/Local/Server-Lib-ROM" "Server-Lib-ROM:"
echo -------------------------------------------

echo -------------------------------------------
echo Sync [PUSH] Server-Perforce
rclone sync --progress --bwlimit 100M --copy-links "C:/Users/marca/Server/Local/Server-Perforce" "Server-Perforce:"
echo -------------------------------------------

echo -------------------------------------------
echo Sync [PUSH] Server-Lib-Media
rclone sync --progress --bwlimit 100M --copy-links --delete-before "C:/Users/marca/Server/Local/Server-Lib-Media" "Server-Lib-Media:"
echo -------------------------------------------

echo -------------------------------------------
echo Sync [PUSH] Server-System-GOATPC
rclone sync --progress --bwlimit 100M --copy-links "C:/Users/marca/Server/Local/Server-System-GOATPC" "Server-System-GOATPC:"
echo -------------------------------------------


echo -------------------------------------------
echo Sync [PUSH] 3D
rclone sync --progress --bwlimit 100M "C:/Users/marca/Server/Local/Server-Lib-3D" "Server-Lib-3D:"
echo -------------------------------------------




echo COMPLETED SYNC!
pause