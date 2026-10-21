@echo off
REM 打开今天的优惠报表（没有就打开最近一份）
cd /d "%~dp0"

build\venv\Scripts\python.exe -c "import datetime,pathlib,os;p=pathlib.Path('build/reports');t=p/(datetime.date.today().isoformat()+'.html');f=t if t.exists() else (max(p.glob('*.html'),key=lambda x:x.stat().st_mtime) if list(p.glob('*.html')) else None);print(f.resolve() if f else 'NO_REPORT');os.startfile(f) if f else None"

if errorlevel 1 pause
