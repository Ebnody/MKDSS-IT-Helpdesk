@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo Python 3 is required. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo MKDSS IT Helpdesk is installed.
echo Start with: START_SERVER.bat
pause
