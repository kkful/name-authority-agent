@echo off
cd /d "%~dp0"
echo Starting CDP Proxy...
start "" /B node "C:/Users/Administrator/.claude/skills/web-access/scripts/cdp-proxy.mjs"
timeout /t 2 /nobreak >nul
echo Starting author_agent...
start "" /B python server.py
echo Ready. Open http://127.0.0.1:8820
pause
