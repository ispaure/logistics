@echo off
set "repair_drive=%~1"
if not defined repair_drive set "repair_drive=D:"
echo Repairing %repair_drive%
chkdsk %repair_drive% /f /r
pause
