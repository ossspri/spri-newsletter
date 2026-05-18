@echo off
REM SPRi Newsletter — Portable 셋업 스크립트 (동료 PC 초기 1회 실행)
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
echo  SPRi Newsletter — 동료 PC 초기 셋업
echo  작업 디렉토리: %ROOT%
echo ============================================================
echo.

REM ── 1. .env 준비 ──
if not exist ".env" (
    if not exist ".env.example" (
        echo [ERROR] .env.example 가 없습니다. zip 패키지가 손상되었을 수 있습니다.
        goto :fail
    )
    echo [STEP 1/5] .env 가 없습니다. .env.example 을 복사합니다.
    copy /Y ".env.example" ".env" >nul
    echo          메모장으로 .env 를 엽니다. CLAUDE_API_KEY 등을 입력 후 저장하고 닫아주세요.
    start /WAIT notepad ".env"
) else (
    echo [STEP 1/5] .env 가 이미 존재합니다. 건너뜁니다.
)

REM ── 2. credentials\google_credentials.json 확인 ──
if not exist "credentials\google_credentials.json" (
    echo.
    echo [ERROR] credentials\google_credentials.json 이 없습니다.
    echo         Google Cloud Console 에서 OAuth Desktop client JSON 을 받아
    echo         credentials\ 폴더에 위 이름으로 배치한 뒤 다시 실행하세요.
    goto :fail
) else (
    echo [STEP 2/5] credentials\google_credentials.json 확인 OK.
)

REM ── 3. Python 설치 확인 ──
echo [STEP 3/5] Python 설치 확인 중...
call "%~dp0install_python.bat"
if errorlevel 1 goto :fail

REM install_python.bat 의 setlocal 로 PATH 가 복원되므로 여기서 다시 갱신
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=%%B;%PATH%"
set "PYTHON_HOME=%LOCALAPPDATA%\Programs\Python\Python311"
if exist "%PYTHON_HOME%\python.exe" set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%PATH%"

REM ── 4. venv 생성 + 의존성 설치 ──
if not exist ".venv\Scripts\python.exe" (
    echo [STEP 4/5] .venv 가상환경 생성 중...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] python -m venv 실패. Python 3.11+ 가 PATH 에 있는지 확인하세요.
        goto :fail
    )
) else (
    echo [STEP 4/5] .venv 가 이미 존재합니다. 의존성만 동기화합니다.
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install 실패. 사내 프록시 / CA 인증서 설정을 확인하세요.
    echo         (docs\TROUBLESHOOTING.md 의 "pip SSL/사내 프록시" 절 참고)
    goto :fail
)

REM ── 4. 첫 OAuth 트리거 ──
echo.
echo [STEP 5/5] 첫 OAuth 동의를 위해 server 를 잠시 띄웁니다.
echo.
echo          *** 중요 ***
echo          브라우저가 열리면 [팀 공용 Gmail 계정]으로 로그인하세요.
echo          개인 Gmail이 아닙니다! (계정 정보는 메인 운영자에게 확인)
echo          "다른 계정 사용" 을 클릭하면 계정을 선택할 수 있습니다.
echo.
echo          동의 후 창을 닫지 마세요.
echo          서버는 30초 후 자동 종료됩니다. (start_server.bat 로 다시 시작 가능)
echo.

set SPRI_CONFIG=config.windows-portable.yaml
start "spri-oauth-bootstrap" /B cmd /c ".venv\Scripts\python.exe main.py --mode server"

REM 30초 대기 후 5000 포트 LISTEN 프로세스 종료
timeout /t 30 /nobreak >nul
call "%~dp0stop_server.bat" >nul 2>&1

echo.
echo ============================================================
echo  셋업이 완료되었습니다.
echo  이후엔 start_server.bat 더블클릭만 하면 됩니다.
echo  접속 주소: http://127.0.0.1:5000
echo ============================================================
echo.
popd
endlocal
pause
exit /b 0

:fail
echo.
echo ============================================================
echo  셋업 실패. 위 오류 메시지를 확인하세요.
echo  도움말: docs\TROUBLESHOOTING.md
echo ============================================================
popd
endlocal
pause
exit /b 1
