@echo off
REM SPRi Newsletter — 일상 사용 진입점 (Web UI 기동)
chcp 65001 >nul

setlocal
pushd "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv 가 없습니다. 먼저 scripts\win\setup_local.bat 을 실행하세요.
    popd
    endlocal
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env 가 없습니다. 먼저 scripts\win\setup_local.bat 을 실행하세요.
    popd
    endlocal
    pause
    exit /b 1
)

set SPRI_CONFIG=config.windows-portable.yaml
echo ============================================================
echo  SPRi Newsletter Server 시작
echo  URL: http://127.0.0.1:5000
echo  종료: 이 창을 닫거나 scripts\win\stop_server.bat 실행
echo  CONFIG: %SPRI_CONFIG%
echo ============================================================
echo.

".venv\Scripts\python.exe" main.py --mode server

popd
endlocal
pause
