@echo off
setlocal
REM ============================================================
REM  ima-knowledge / launcher  (DOUBLE-CLICK THIS FILE)
REM
REM  THIS FILE MUST STAY 100% ASCII.
REM  cmd.exe parses .bat using the ANSI codepage (936/GBK here),
REM  while the console runs 65001/UTF-8 - the two disagree, so any
REM  CJK byte inside this file corrupts the parse. All Chinese text
REM  is printed by tools\sync.py instead (verified 2026-10-06).
REM
REM  Usage:  sync.bat          (interactive, pauses at the end)
REM          sync.bat /auto    (silent, for Task Scheduler)
REM ============================================================

chcp 65001 >nul 2>&1

set "REPO=%~dp0"
set "PY="

where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    if exist "C:\Users\Cheng\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
        set "PY=C:\Users\Cheng\.workbuddy\binaries\python\versions\3.13.12\python.exe"
    )
)
if not defined PY (
    echo.
    echo   [ERROR] Python not found. Install Python 3 or fix PATH.
    echo.
    pause
    exit /b 1
)

%PY% "%REPO%tools\sync.py" --repo "%REPO%." %*
set "RC=%ERRORLEVEL%"

if "%RC%"=="1" (
    echo.
    echo   [ERROR] Sync failed. Log: %REPO%_meta\sync.log
)
if "%RC%"=="2" (
    echo.
    echo   [OK] Nothing to push - already up to date.
)

if /i "%~1"=="/auto" exit /b %RC%
echo.
echo   Press any key to close...
pause >nul
exit /b %RC%
