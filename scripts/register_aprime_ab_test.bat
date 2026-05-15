@echo off
REM scripts/register_aprime_ab_test.bat
REM   Windows Task Scheduler에 AprimeABTest 등록 (1주일 누적 측정용)
REM   매일 06:30 KST 자동 실행 - GAS B newsletter 발송(~06:25) 직후
REM   비교 측정만 수행, 실제 발송에는 영향 없음
REM
REM 사용:
REM   1. 한 번만 실행: scripts\register_aprime_ab_test.bat
REM   2. 등록 확인: schtasks /Query /TN "AprimeABTest"
REM   3. 즉시 실행 테스트: schtasks /Run /TN "AprimeABTest"
REM   4. 등록 해제: schtasks /Delete /TN "AprimeABTest" /F

chcp 65001 >nul

set PYTHON_EXE=C:\Users\martin.hs.yoo\AppData\Local\Programs\Python\Python311\python.exe
set PROJECT_DIR=C:\Users\martin.hs.yoo\dev\newsletter_system
set SCRIPT=%PROJECT_DIR%\scripts\daily_ab_test.py

echo ============================================
echo AprimeABTest Task Scheduler 등록
echo ============================================
echo Python:  %PYTHON_EXE%
echo Script:  %SCRIPT%
echo Trigger: Daily 06:30
echo ============================================

REM /TR 인자는 "python.exe script.py" 형태로 전달
REM 따옴표 처리: schtasks는 /TR 값에 따옴표가 있으면 \" 이스케이프 필요
schtasks /Create /TN "AprimeABTest" ^
  /TR "\"%PYTHON_EXE%\" \"%SCRIPT%\"" ^
  /SC DAILY ^
  /ST 06:30 ^
  /RL HIGHEST ^
  /F

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo [ERROR] 등록 실패. 관리자 권한으로 다시 실행하거나 schtasks 출력 확인.
  pause
  exit /b 1
)

echo.
echo [OK] 등록 완료. 등록 정보:
echo.
schtasks /Query /TN "AprimeABTest" /V /FO LIST | findstr /B /C:"TaskName" /C:"Next Run Time" /C:"Status" /C:"Schedule Type" /C:"Start Time"

echo.
echo 즉시 한 번 실행해서 동작 확인하려면:
echo   schtasks /Run /TN "AprimeABTest"
echo.
pause
