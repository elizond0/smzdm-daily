@echo off
REM 值得买每日优惠推送
REM 幂等：当天已经推送过就不会重复推送（--force 可强制）
REM 直接双击运行，也可以由定时任务调用
cd /d "%~dp0"

if not exist build\venv\Scripts\python.exe (
  echo [错误] 未找到运行环境 build\venv
  echo 请先执行: python -m venv build\venv
  pause
  exit /b 1
)

build\venv\Scripts\python.exe daily.py %*
echo.
if "%~1"=="" pause
