@echo off
cd /d "%~dp0"
start "" /B python server.py
echo author_agent started at http://127.0.0.1:8820
pause
