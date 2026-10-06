@echo off
setlocal
cd /d "%~dp0"
if not exist "instance\backups" mkdir "instance\backups"
for /f "tokens=1-3 delims=/" %%a in ("%date%") do set D=%%c-%%b-%%a
copy /Y "instance\mkdss_helpdesk.sqlite3" "instance\backups\mkdss_helpdesk_%D%.sqlite3"
echo Backup completed.
pause
