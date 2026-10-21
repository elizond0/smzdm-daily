@echo off
setlocal
cd /d "%~dp0"

REM ==========================================================
REM  Push this repo to GitHub.
REM  Keep this file pure ASCII. Chinese characters get truncated
REM  by cmd and the script breaks into garbage commands.
REM ==========================================================

set "GITHUB_USER=elizond0"
set "REPO_NAME=smzdm-daily"

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
  echo [ERROR] git.exe not found.
  start "" mshta "javascript:alert('Deploy FAILED - git.exe not found');close()" >nul 2>&1
  pause
  exit /b 1
)

set "GH_TOKEN="
if exist "%~dp0.deploy.token" (
  set /p GH_TOKEN=<"%~dp0.deploy.token"
)

if not defined GH_TOKEN (
  echo [ERROR] .deploy.token not found in this folder.
  start "" mshta "javascript:alert('Deploy FAILED - token file missing');close()" >nul 2>&1
  pause
  exit /b 1
)

echo Using git: %GIT%
echo Target : https://github.com/%GITHUB_USER%/%REPO_NAME%.git
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
echo Repo: https://github.com/%GITHUB_USER%/%REPO_NAME%
echo Site: https://%GITHUB_USER%.github.io/%REPO_NAME%/
echo.
echo Cloud will run automatically at 20:00 every day.
echo.
start "" mshta "javascript:alert('Deploy SUCCESS - code is on GitHub, cloud runs daily at 20:00');close()" >nul 2>&1
pause
exit /b 0

:fail
echo.
echo [FAILED] Push did not succeed.
echo   Token needs BOTH scopes: repo + workflow
echo   Also check repo name and user name.
echo.
start "" mshta "javascript:alert('Deploy FAILED - token needs repo + workflow scopes');close()" >nul 2>&1
pause
exit /b 1
