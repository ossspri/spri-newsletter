@echo off
REM SPRi Newsletter — 5000 포트 LISTEN 프로세스 종료
chcp 65001 >nul

setlocal enabledelayedexpansion

set FOUND=0
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:"LISTENING" ^| findstr ":5000 "') do (
    if not "%%P"=="0" (
        echo [INFO] PID %%P 를 종료합니다.
        taskkill /F /PID %%P >nul 2>&1
        set FOUND=1
    )
)

if !FOUND!==0 (
    echo [INFO] 포트 5000 에서 LISTEN 중인 프로세스가 없습니다.
)

endlocal
exit /b 0
