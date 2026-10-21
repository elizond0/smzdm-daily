@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   Push local repo to GitHub
echo ==========================================
echo.
echo BEFORE YOU START:
echo   Create an EMPTY repository on GitHub
echo   (do NOT check "Add a README", ".gitignore" or "license")
echo.
echo Suggested repo name: smzdm-daily
echo.

set "GITHUB_USER="
set "REPO_NAME="

set /p GITHUB_USER=GitHub username: 
if "%GITHUB_USER%"=="" goto abort

set /p REPO_NAME=Repo name: 
if "%REPO_NAME%"=="" goto abort

echo.
echo Target: https://github.com/%GITHUB_USER%/%REPO_NAME%.git
echo.

git remote remove origin >nul 2>&1
git remote add origin "https://github.com/%GITHUB_USER%/%REPO_NAME%.git"
git branch -M main

echo Pushing... (a browser window may pop up for GitHub login)
echo.
git push -u origin main

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
echo [FAILED] Push did not succeed. Common reasons:
echo   - repo not created yet, or name misspelled
echo   - login popup was closed
echo   - repo is not empty (it already has a README)
echo.
pause
exit /b 1

:abort
echo.
echo Cancelled: username and repo name are required.
pause
exit /b 1
