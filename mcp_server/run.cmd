@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not defined MCP_PORT set MCP_PORT=8931

rem Prefer a known install path over the Windows Store python stub
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo ============================================================
echo  Plant Structure MCP Server  (SSE)
echo  local : http://127.0.0.1:%MCP_PORT%/sse
echo  nexent: http://host.docker.internal:%MCP_PORT%/sse
echo  Press Ctrl+C to stop
echo ============================================================
"%PYEXE%" server.py
echo.
echo [server exited] code=%errorlevel%
pause
