@echo off
chcp 65001 >nul
title Nexent 一键修复
echo.
echo   正在通过 WSL 修复 Nexent（大约 1 分钟）...
echo.

for /f "usebackq tokens=*" %%i in (`wsl -d Ubuntu wslpath -a "%~dp0restart-nexent.sh"`) do set "WPATH=%%i"

if "%WPATH%"=="" (
    echo   [错误] 找不到 WSL 发行版 Ubuntu，或者 WSL 没启动。
    pause
    exit /b 1
)

wsl -d Ubuntu -- bash "%WPATH%"

echo.
echo   按任意键退出...
pause >nul
