@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set HOST=0.0.0.0
set PORT=5001
echo.
echo =============================================================
echo MKDSS IT HELPDESK - PROFESSIONAL UI v2.5.9
echo =============================================================
echo This build uses port 5001 so an older Helpdesk
echo server still running on port 5000 cannot mask this build.
echo.
echo Local: http://127.0.0.1:5001/dashboard
echo LAN:   http://SERVER-IP:5001/dashboard
echo.
python app.py --host %HOST% --port %PORT%
pause
