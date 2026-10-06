@echo off
chcp 65001 >nul 2>&1
setlocal

REM ============================================================
REM  ima-knowledge / push local export to GitHub
REM
REM  ENCODING: this file is UTF-8 (no BOM). cmd.exe decodes .bat
REM  with the ANSI codepage (936/GBK on this box) - that is why
REM  `chcp 65001` is the FIRST statement, before any CJK text.
REM  Everything above this line MUST stay pure ASCII or the whole
REM  file fails to parse (same trap as D:\dsa\sync.bat, 2026-09-08).
REM
REM  Usage:
REM    sync.bat          -> interactive (pauses at the end)
REM    sync.bat /auto    -> silent (for Task Scheduler)
REM
REM  Log: <repo>\_meta\sync.log
REM ============================================================

set "REPO=%~dp0."
set "META=%~dp0_meta"
set "LOGFILE=%META%\sync.log"
if not exist "%META%" mkdir "%META%" 2>nul

if not defined HOME set "HOME=%USERPROFILE%"
set "GIT_TERMINAL_PROMPT=0"
REM  port 22 is refused on this network - force ssh over 443
if not defined GIT_SSH_COMMAND set "GIT_SSH_COMMAND=ssh -p 443 -o StrictHostKeyChecking=accept-new"

set "STAMP=%date% %time%"

call :log "============================================================"
call :log "[%STAMP%] === sync start ==="

echo.
echo   ima 知识库 -> GitHub 同步
echo   ----------------------------------------

REM ---------- [0/5] preflight ----------
echo [0/5] 环境检查...

where git >nul 2>&1
if errorlevel 1 (
    echo   [错误] 没有找到 git，请先安装 Git for Windows。
    call :log "[%STAMP%] FAILED - git not found"
    goto :fail
)

if not exist "%REPO%\.git\" (
    echo   [错误] %REPO% 不是 git 仓库。
    call :log "[%STAMP%] FAILED - not a git repo: %REPO%"
    goto :fail
)

git -C "%REPO%" remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo   [错误] 仓库没有配置 origin 远程地址。
    call :log "[%STAMP%] FAILED - no origin remote"
    goto :fail
)

for /f "delims=" %%i in ('git -C "%REPO%" remote get-url origin') do set "ORIGIN=%%i"
for /f "delims=" %%i in ('git -C "%REPO%" rev-parse --abbrev-ref HEAD') do set "BRANCH=%%i"
echo   仓库: %REPO%
echo   远程: %ORIGIN%
echo   分支: %BRANCH%

REM ---------- [1/5] git add ----------
echo [1/5] 暂存改动 (git add -A) ...
git -C "%REPO%" add -A >>"%LOGFILE%" 2>&1
if errorlevel 1 (
    echo   [错误] git add 失败，详见日志。
    call :log "[%STAMP%] FAILED - git add"
    goto :fail
)

git -C "%REPO%" diff --cached --quiet
if not errorlevel 1 (
    echo.
    echo   没有检测到改动，无需推送。
    call :log "[%STAMP%] no changes - skipped"
    goto :done
)

REM ---------- [2/5] stats ----------
echo [2/5] 统计变更...
set "N=0"
for /f "delims=" %%a in ('git -C "%REPO%" diff --cached --name-only') do set /a "N+=1"
echo   待提交文件: %N% 个
call :log "[%STAMP%] staged %N% file(s)"

REM ---------- [3/5] commit ----------
echo [3/5] 提交 (git commit) ...
git -C "%REPO%" commit -m "ima sync %STAMP% (%N% files)" >>"%LOGFILE%" 2>&1
if errorlevel 1 (
    echo   [错误] git commit 失败，详见日志。
    call :log "[%STAMP%] FAILED - git commit"
    goto :fail
)

REM ---------- [4/5] pull --rebase ----------
echo [4/5] 拉取远端并变基 (pull --rebase) ...
git -C "%REPO%" pull --rebase origin %BRANCH% >>"%LOGFILE%" 2>&1
if errorlevel 1 (
    echo   [警告] rebase 冲突，已自动回滚，本地提交保留。
    git -C "%REPO%" rebase --abort >>"%LOGFILE%" 2>&1
    call :log "[%STAMP%] FAILED - rebase conflict, aborted"
    goto :fail
)

REM ---------- [5/5] push ----------
echo [5/5] 推送到 GitHub (git push) ...
git -C "%REPO%" push origin %BRANCH% >>"%LOGFILE%" 2>&1
if not errorlevel 1 goto :ok

echo   首次推送失败，10 秒后重试...
call :log "[%STAMP%] first push failed, retrying"
ping -n 11 127.0.0.1 >nul 2>&1
git -C "%REPO%" push origin %BRANCH% >>"%LOGFILE%" 2>&1
if not errorlevel 1 goto :ok

call :log "[%STAMP%] FAILED - git push"
goto :fail

:ok
echo.
echo   [完成] 已推送到 GitHub。  %STAMP%
echo   共提交 %N% 个文件。
call :log "[%STAMP%] SUCCESS - pushed %N% file(s)"
goto :done

:fail
echo.
echo   [失败] 同步未成功。日志: %LOGFILE%

:done
call :log "[%STAMP%] === sync end ==="
if /i "%~1"=="/auto" goto :eof
echo.
echo   按任意键关闭...
pause >nul
goto :eof

:log
echo %~1>>"%LOGFILE%"
goto :eof
