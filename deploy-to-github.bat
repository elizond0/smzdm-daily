@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   Push local repo to GitHub
echo ==========================================
echo.

REM ---- Locate git.exe (system PATH may not have it) ----
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
  echo [ERROR] git.exe not found on this machine.
  echo.
  echo Install Git for Windows first: https://git-scm.com/download/win
  echo After installing, run this script again.
  echo.
  pause
  exit /b 1
)

echo Using git: %GIT%
echo.
echo BEFORE YOU START - two things:
echo   1) Create an EMPTY repo on GitHub (no README / .gitignore / license)
echo      Suggested name: smzdm-daily
echo   2) Create a token: https://github.com/settings/tokens
echo      "Generate new token (classic)" - tick the "repo" scope
echo.

set "GITHUB_USER="
set "REPO_NAME="
set "GH_TOKEN="

set /p GITHUB_USER=GitHub username: 
if "%GITHUB_USER%"=="" goto abort

set /p REPO_NAME=Repo name: 
if "%REPO_NAME%"=="" goto abort

set /p GH_TOKEN=Paste token (ghp_...): 
if "%GH_TOKEN%"=="" goto abort

echo.
echo Pushing to https://github.com/%GITHUB_USER%/%REPO_NAME%.git ...
echo (the token is only used for this one command, nothing is saved)
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
echo Now finish these 3 steps on your repo page:
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
echo   3) Actions tab - "Run workflow" to test manually
echo.
pause
exit /b 0

:fail
echo.
echo [FAILED] Push did not succeed. Check:
echo   - repo exists and the name is spelled right
echo   - the token is copied completely (starts with ghp_)
echo   - the token has the "repo" scope
echo   - the repo is empty (no README created)
echo.
pause
exit /b 1

:abort
echo.
echo Cancelled: username, repo name and token are all required.
pause
exit /b 1
