@echo off
REM SPRi Newsletter — Python 자동 설치 스크립트
REM setup_local.bat 에서 호출되며, Python이 없으면 자동 다운로드 + 설치합니다.
REM 이미 설치되어 있으면 즉시 종료합니다.
chcp 65001 >nul

setlocal

REM ── 설정 ──
set PYTHON_VERSION=3.11.9
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set INSTALLER=%TEMP%\python-%PYTHON_VERSION%-amd64.exe

REM ── 1. Python 설치 여부 확인 ──
python --version >nul 2>&1
if not errorlevel 1 (
    echo [Python] 이미 설치되어 있습니다:
    python --version
    endlocal
    exit /b 0
)

REM py launcher 확인 (Python이 PATH에 없어도 py는 있을 수 있음)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    echo [Python] py launcher로 접근 가능:
    py -3 --version
    endlocal
    exit /b 0
)

REM ── 2. Python 미설치 — 다운로드 + 설치 진행 ──
echo.
echo ============================================================
echo  Python %PYTHON_VERSION% 자동 설치
echo ============================================================
echo.
echo  Python이 설치되어 있지 않습니다.
echo  python.org 에서 자동 다운로드하여 설치합니다.
echo  (인터넷 연결 필요, 관리자 권한 불필요)
echo.

REM ── 3. 다운로드 ──
echo [1/3] Python %PYTHON_VERSION% 다운로드 중...
echo       URL: %PYTHON_URL%
echo       저장: %INSTALLER%
echo.

curl -L -o "%INSTALLER%" "%PYTHON_URL%" --progress-bar
if errorlevel 1 (
    echo.
    echo [ERROR] 다운로드 실패. 인터넷 연결 또는 사내 프록시를 확인하세요.
    echo.
    echo         수동 설치 방법:
    echo         1. https://www.python.org/downloads/ 접속
    echo         2. Python 3.11.x 다운로드 후 설치
    echo         3. 설치 시 "Add python.exe to PATH" 반드시 체크
    echo         4. 설치 완료 후 setup_local.bat 다시 실행
    echo.
    endlocal
    exit /b 1
)

REM 파일 크기 확인 (너무 작으면 다운로드 실패)
for %%F in ("%INSTALLER%") do set FILESIZE=%%~zF
if %FILESIZE% LSS 1000000 (
    echo [ERROR] 다운로드된 파일이 비정상적으로 작습니다 (%FILESIZE% bytes).
    echo         프록시가 로그인 페이지를 반환했을 수 있습니다.
    del "%INSTALLER%" >nul 2>&1
    endlocal
    exit /b 1
)

REM ── 4. Silent Install ──
echo [2/3] Python %PYTHON_VERSION% 설치 중... (1-2분 소요)
echo       설치 옵션: 현재 사용자 전용, PATH 자동 추가
echo.

"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1
if errorlevel 1 (
    echo.
    echo [ERROR] Python 설치 실패 (에러코드: %errorlevel%).
    echo         디스크 공간 또는 권한 문제일 수 있습니다.
    echo.
    echo         수동 설치: %INSTALLER% 를 직접 더블클릭하여 설치하세요.
    echo         설치 시 "Add python.exe to PATH" 반드시 체크!
    endlocal
    exit /b 1
)

REM ── 5. PATH 갱신 (현재 세션에 반영) ──
echo [3/3] PATH 갱신 중...

REM 사용자 PATH를 레지스트리에서 다시 읽어 현재 세션에 반영
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
set "PATH=%USER_PATH%;%PATH%"

REM Python 설치 기본 경로도 직접 추가 (PATH 반영 지연 대비)
set "PYTHON_HOME=%LOCALAPPDATA%\Programs\Python\Python311"
if exist "%PYTHON_HOME%\python.exe" (
    set "PATH=%PYTHON_HOME%;%PYTHON_HOME%\Scripts;%PATH%"
)

REM ── 6. 설치 확인 ──
python --version >nul 2>&1
if errorlevel 1 (
    REM py launcher로 재시도
    py -3 --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERROR] Python 설치는 완료되었으나 PATH에서 찾을 수 없습니다.
        echo         이 CMD 창을 닫고 setup_local.bat 을 다시 실행해 주세요.
        echo         (새 CMD 창에서는 PATH 가 적용됩니다)
        del "%INSTALLER%" >nul 2>&1
        endlocal
        exit /b 1
    )
)

echo.
echo [SUCCESS] Python 설치 완료:
python --version
pip --version
echo.

REM ── 7. 임시 파일 삭제 ──
del "%INSTALLER%" >nul 2>&1

endlocal
exit /b 0
