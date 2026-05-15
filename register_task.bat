@echo off
chcp 65001 >nul
schtasks /create /tn "SPRi_Daily_Newsletter" /xml "%~dp0task_schedule.xml" /f
pause
