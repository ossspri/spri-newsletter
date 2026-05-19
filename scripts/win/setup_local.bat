@echo off
REM SPRi Newsletter - Setup script (one-file bootstrap + in-repo setup)
REM
REM Two run modes (auto-detected):
REM   (A) Bootstrap mode: this .bat was downloaded standalone (e.g. to Desktop).
REM       -> install Git (if missing), git clone repo to C:\spri-newsletter,
REM          wait for email-attached secrets, then chain into the cloned copy.
REM   (B) In-repo mode: this .bat lives inside a cloned repo
REM       (scripts\win\setup_local.bat). Runs the 6-step setup directly.
chcp 65001 >nul

REM Detect mode: if requirements.txt is two levels up, we are in-repo.
if defined SPRI_BOOTSTRAP_DONE goto :in_repo_start
if exist "%~dp0..\..\requirements.txt" goto :in_repo_start

REM ============================================================
REM (A) Bootstrap mode
REM ============================================================
setlocal
set TARGET_DIR=C:\spri-newsletter
set REPO_URL=https://github.com/ossspri/spri-newsletter.git
set RAW_BASE=https://raw.githubusercontent.com/ossspri/spri-newsletter/main/scripts/win

echo(
echo ============================================================
echo  SPRi Newsletter - Bootstrap (first-time install)
echo  Target: %TARGET_DIR%
echo ============================================================
echo(

REM -- Bootstrap 1/3: ensure Git --
git --version >nul 2>&1
if not errorlevel 1 goto :bs_have_git

echo [Bootstrap 1/3] Git not found. Downloading installer helper ...
curl -L -o "%TEMP%\install_git.bat" "%RAW_BASE%/install_git.bat" --ssl-no-revoke
if errorlevel 1 goto :bs_dl_failed
call "%TEMP%\install_git.bat"
if errorlevel 1 goto :bs_git_failed
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
git --version >nul 2>&1
if errorlevel 1 goto :bs_git_failed

:bs_have_git
echo [Bootstrap 1/3] Git OK.
git --version

REM -- Bootstrap 2/3: clone repo --
if exist "%TARGET_DIR%\.git" goto :bs_clone_skip
if exist "%TARGET_DIR%" goto :bs_dir_conflict

echo(
echo [Bootstrap 2/3] Cloning %REPO_URL% ...
git clone %REPO_URL% "%TARGET_DIR%"
if errorlevel 1 goto :bs_clone_failed
goto :bs_clone_done

:bs_clone_skip
echo(
echo [Bootstrap 2/3] %TARGET_DIR% already cloned. Reusing.

:bs_clone_done

REM -- Bootstrap 3/3: wait for email-attached secret files --
:bs_wait_secrets
echo(
echo [Bootstrap 3/3] Place email-attached secret files now:
echo    .env                       -^> %TARGET_DIR%\.env
echo    google_credentials.json    -^> %TARGET_DIR%\credentials\google_credentials.json
echo(
echo  After copying BOTH files, press any key to continue.
echo  (Ctrl+C to abort; you can re-run this script later.)
pause >nul

if not exist "%TARGET_DIR%\.env" (
    echo [WARN] .env not found yet.
    goto :bs_wait_secrets
)
if not exist "%TARGET_DIR%\credentials\google_credentials.json" (
    echo [WARN] credentials\google_credentials.json not found yet.
    goto :bs_wait_secrets
)

REM -- Chain into cloned setup_local.bat (in-repo mode) --
set SPRI_BOOTSTRAP_DONE=1
echo(
echo ============================================================
echo  Bootstrap done. Launching in-repo setup ...
echo ============================================================
echo(
call "%TARGET_DIR%\scripts\win\setup_local.bat"
set RC=%ERRORLEVEL%
endlocal & exit /b %RC%

:bs_dl_failed
echo(
echo [ERROR] Failed to download install_git.bat. Check internet / proxy.
endlocal
pause
exit /b 1

:bs_git_failed
echo(
echo [ERROR] Git auto-install failed.
echo         Install Git manually from https://git-scm.com/download/win
echo         then re-run this script.
endlocal
pause
exit /b 1

:bs_dir_conflict
echo(
echo [ERROR] %TARGET_DIR% exists but is not a git repository.
echo         Remove or rename it, then re-run.
endlocal
pause
exit /b 1

:bs_clone_failed
echo(
echo [ERROR] git clone failed. Check internet / proxy / repo access.
endlocal
pause
exit /b 1

REM ============================================================
REM (B) In-repo mode (existing 6-step setup)
REM ============================================================
:in_repo_start
setlocal
pushd "%~dp0..\.."
set ROOT=%CD%

echo.
echo ============================================================
echo  SPRi Newsletter - Setup
echo  Working directory: %ROOT%
echo ============================================================
echo.

REM --- 0. Git installation check ---
echo [STEP 1/6] Checking Git installation...
call "%~dp0install_git.bat"
if errorlevel 1 goto :fail
for /f "tokens=2*" %%A in ('reg query "HKLM\Software\Microsoft\Windows\CurrentVersion\App Paths\git.exe" /ve 2^>nul') do set "GIT_EXE=%%B"
if exist "%ProgramFiles%\Git\cmd\git.exe" set "PATH=%ProgramFiles%\Git\cmd;%PATH%"

REM ── 1. .env 준비 ──
if exist ".env" goto :env_exists
if not exist ".env.example" goto :env_example_missing
echo [STEP 2/6] .env not found. Copying from .env.example ...
copy /Y ".env.example" ".env" >nul
echo          Opening .env in Notepad. Enter API keys, save, then close.
start /WAIT notepad ".env"
goto :env_done

:env_example_missing
echo [ERROR] .env.example not found. Package may be corrupted.
goto :fail

:env_exists
echo [STEP 2/6] .env already exists. Skipping.

:env_done

REM ── 2. credentials\google_credentials.json 확인 ──
if exist "credentials\google_credentials.json" goto :cred_ok
echo.
echo [ERROR] credentials\google_credentials.json not found.
echo         Place the google_credentials.json file you received by email
echo         into the credentials\ folder, then re-run this script.
echo         (Get OAuth Desktop client JSON from Google Cloud Console
echo          if you are setting up from scratch.)
goto :fail

:cred_ok
echo [STEP 3/6] credentials\google_credentials.json OK.

REM ── 3. Python 설치 확인 ──
echo [STEP 4/6] Checking Python installation...
call "%~dp0install_python.bat"
if errorlevel 1 goto :fail

REM install_python.bat uses setlocal, so PATH reverts. Refresh here.
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=%%B;%PATH%"
set "PYTHON_HOME=%LOCALAPPDATA%\Programs\Python\Python311"
if exist "%PYTHON_HOME%\python.exe" set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%PATH%"

REM ── 4. venv 생성 + 의존성 설치 ──
if exist ".venv\Scripts\python.exe" goto :venv_exists
echo [STEP 5/6] .venv creating virtual environment...
python -m venv .venv
if errorlevel 1 goto :venv_fail
goto :venv_ready

:venv_fail
echo [ERROR] python -m venv failed. Ensure Python 3.11+ is in PATH.
goto :fail

:venv_exists
echo [STEP 5/6] .venv already exists. Syncing dependencies only.

:venv_ready
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 goto :pip_fail
goto :pip_ok

:pip_fail
echo [ERROR] pip install failed. Check proxy / CA cert settings.
echo         See docs\TROUBLESHOOTING.md
goto :fail

:pip_ok

REM ── 5. First OAuth trigger ──
echo.
echo [STEP 6/6] Starting server for first-time OAuth consent...
echo.
echo          *** IMPORTANT ***
echo          When the browser opens, log in with the TEAM Gmail account.
echo          NOT your personal Gmail!
echo          Click "Use another account" if needed.
echo.
echo          Do NOT close the browser window after consent.
echo          Server will auto-stop after 30 seconds.
echo.

set SPRI_CONFIG=config.windows-portable.yaml
start "spri-oauth-bootstrap" /B cmd /c ".venv\Scripts\python.exe main.py --mode server"

REM Wait 30s then stop the server
timeout /t 30 /nobreak >nul
call "%~dp0stop_server.bat" >nul 2>&1

echo.
echo ============================================================
echo  Setup completed successfully!
echo  From now on, just double-click start_server.bat
echo  URL: http://127.0.0.1:5000
echo ============================================================
echo.
popd
endlocal
pause
exit /b 0

:fail
echo.
echo ============================================================
echo  Setup FAILED. Check the error message above.
echo  Help: docs\TROUBLESHOOTING.md
echo ============================================================
popd
endlocal
pause
exit /b 1
