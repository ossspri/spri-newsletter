@echo off
chcp 65001 >nul
cd /d "C:\Users\martin.hs.yoo\dev\newsletter_system"
set PYEXE="C:\Users\martin.hs.yoo\AppData\Local\Programs\Python\Python311\python.exe"

REM Step 1: Daily newsletter send (cron idempotent guard)
%PYEXE% main.py --mode daily --cron >> logs\cron.log 2>&1

REM Step 2: A/A'/B quality measurement (B published from 06:00, runs after daily)
%PYEXE% scripts\daily_ab_test.py >> logs\cron.log 2>&1
