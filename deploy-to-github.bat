@echo off
setlocal
cd /d "%~dp0"

REM ==========================================================
REM  推送本仓库到 GitHub
REM  账号信息已写在下面，Token 从 .deploy.token 读取
REM  （该文件被 .gitignore 排除，不会上传）
REM ==========================================================

set "GITHUB_USER=elizond0"
set "REPO_NAME=smzdm-daily"

echo.
echo ==========================================
echo   Push local repo to GitHub
echo ==========================================
echo.

REM ---- 自动定位 git.exe（系统 PATH 里没有） ----
set "GIT="
set "PF86=%ProgramFiles(x86)%"

if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT if exist "%PF86%\Git\cmd\git.exe" set "GIT=%PF86%\Git\cmd\git.exe"
if not defined GIT if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"

if not defined GIT (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\*") do (
    if exist "%%D\cmd\git.exe" set "GIT=%%D\cmd\git.exe"
  )
)
if not defined GIT (
  for /d %%D in ("%LOCALAPPDATA%\Programs\PortableGit\*") do (
    if exist "%%D\cmd\git.exe" set "GIT=%%D\cmd\git.exe"
  )
)

if not defined GIT (
  echo [ERROR] git.exe not found.
  echo Install Git for Windows: https://git-scm.com/download/win
  pause
  exit /b 1
)

echo Using git: %GIT%

REM ---- 读 Token ----
set "GH_TOKEN="
if exist "%~dp0.deploy.token" (
  set /p GH_TOKEN=<"%~dp0.deploy.token"
)

if not defined GH_TOKEN (
  echo.
  echo [WARN] .deploy.token not found.
  set /p GH_TOKEN=Paste token manually: 
)
if "%GH_TOKEN%"=="" goto abort

echo Target: https://github.com/%GITHUB_USER%/%REPO_NAME%.git
echo Pushing...
echo.

"%GIT%" remote remove origin >nul 2>&1
"%GIT%" remote add origin "https://github.com/%GITHUB_USER%/%REPO_NAME%.git"
"%GIT%" branch -M main

"%GIT%" -c credential.helper= push "https://%GITHUB_USER%:%GH_TOKEN%@github.com/%GITHUB_USER%/%REPO_NAME%.git" main

if errorlevel 1 goto fail

echo.
echo ==========================================
echo   PUSH OK
echo ==========================================
echo.
echo Remaining steps on the repo page:
echo.
echo   1) Settings - Secrets and variables - Actions
echo      New repository secret
echo      Name : SERVERCHAN_SENDKEY
echo      Value: the SCT... string in your config.ini
echo.
echo   2) Settings - Pages
echo      Source: Deploy from a branch
echo      Branch: main     Folder: /docs
echo.
echo   3) Actions tab - "Run workflow" to test
echo.
pause
exit /b 0

:fail
echo.
echo [FAILED] Check:
echo   - token expired or wrong scope (needs "repo")
echo   - repo name / user name wrong
echo   - repo not empty (has a README)
echo.
pause
exit /b 1

:abort
echo.
echo Cancelled: no token available.
pause
exit /b 1
