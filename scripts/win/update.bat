@echo off
REM SPRi Newsletter - Update script (git pull + pip sync)
REM Double-click to fetch latest changes from origin and sync dependencies.
chcp 65001 >nul

setlocal
pushd "%~dp0..\.."
set ROOT=%CD%

echo.
echo ============================================================
echo  SPRi Newsletter - Update
echo  Working directory: %ROOT%
echo ============================================================
echo.

REM -- 1. Check Git --
echo [STEP 1/4] Checking Git installation...
git --version >nul 2>&1
if errorlevel 1 (
    echo          Git not found. Running install_git.bat ...
    call "%~dp0install_git.bat"
    if errorlevel 1 goto :fail
    if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    git --version >nul 2>&1
    if errorlevel 1 goto :git_missing
)
git --version

REM -- 2. git pull --
echo.
echo [STEP 2/4] Pulling latest changes (git pull --ff-only) ...
git pull --ff-only
if errorlevel 1 goto :pull_failed

REM -- 3. venv check + pip install --
echo.
echo [STEP 3/4] Syncing dependencies ...
if not exist ".venv\Scripts\activate.bat" goto :venv_missing
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

REM -- 4. Show recent commits --
echo.
echo [STEP 4/4] Recent commits:
echo ------------------------------------------------------------
git log -5 --pretty=format:"%%h %%s"
echo.
echo ------------------------------------------------------------

echo.
echo ============================================================
echo  Update completed successfully!
echo  Start the server: scripts\win\start_server.bat
echo ============================================================
echo.
popd
endlocal
pause
exit /b 0

:git_missing
echo.
echo [ERROR] Git is required but not available in PATH.
echo         Install Git for Windows: https://git-scm.com/download/win
goto :fail

:pull_failed
echo.
echo [ERROR] git pull failed.
echo         Possible causes:
echo         - Local uncommitted changes (run: git status)
echo         - Network / proxy issue
echo         - Diverged history (contact main PC admin)
goto :fail

:venv_missing
echo.
echo [ERROR] .venv not found. Run scripts\win\setup_local.bat first.
goto :fail

:pip_failed
echo.
echo [ERROR] pip install failed. Check proxy / CA cert settings.
echo         See docs\TROUBLESHOOTING.md
goto :fail

:fail
echo.
echo ============================================================
echo  Update FAILED. Check the error message above.
echo ============================================================
popd
endlocal
pause
exit /b 1
