@echo off
REM ============================================================
REM  Project FORESIGHT - push to GitHub (repo: SR005/foresight)
REM  Prereqs:
REM    1. Git installed:  https://git-scm.com/download/win
REM    2. The empty repo already created at:
REM       https://github.com/SR005/foresight
REM  Then just double-click this file.
REM ============================================================

cd /d "%~dp0"

set REPO=https://github.com/SR005/foresight.git

echo.
echo  Cleaning any broken git folder...
if exist ".git" rmdir /s /q ".git"

echo.
echo  Initialising repository and committing...
git init
git add -A
git commit -m "Project FORESIGHT - demand & inventory intelligence (D1-D7)"
git branch -M main
git remote add origin %REPO%

echo.
echo  Pushing to %REPO%
echo  (A GitHub sign-in window may appear the first time - approve it.)
git push -u origin main

echo.
echo  ============================================================
echo   Done. Code is now at: https://github.com/SR005/foresight
echo   Next - deploy the live dashboard:
echo     1. Go to https://share.streamlit.io  (sign in with GitHub)
echo     2. Create app - Deploy a public app from GitHub
echo     3. Repository : SR005/foresight
echo        Branch     : main
echo        Main file  : app/streamlit_app.py
echo     4. Click Deploy - you get your public URL in ~3 min.
echo  ============================================================
echo.
pause
