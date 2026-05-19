@echo off
REM SPRi Newsletter — Portable 셋업 스크립트 (동료 PC 초기 1회 실행)
REM 0) Git installation check (clone is done via guide; this handles update.bat pre-req)
REM 1) UTF-8 코드페이지 활성 (한글 출력 깨짐 방지)
REM 2) .env 생성 (없으면 .env.example 복사 + 메모장)
REM 3) credentials\google_credentials.json 존재 확인
REM 4) Python 설치 확인 (미설치 시 자동 다운로드+설치)
REM 5) .venv 생성 + requirements 설치
REM 6) 첫 server 기동 → OAuth 브라우저 트리거
chcp 65001 >nul

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
