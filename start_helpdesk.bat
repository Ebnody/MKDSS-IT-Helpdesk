@echo off
cd /d "C:\Users\hp\Downloads\MKDSS Projects\MKDSS IT Helpdesk"

"C:\Users\hp\Downloads\MKDSS Projects\MKDSS IT Helpdesk\.venv\Scripts\python.exe" -m waitress --host=0.0.0.0 --port=5001 app:app