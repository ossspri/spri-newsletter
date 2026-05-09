@echo off
chcp 65001 >nul
cd /d "C:\Users\martin.hs.yoo\dev\newsletter_system"
"C:\Users\martin.hs.yoo\AppData\Local\Programs\Python\Python311\python.exe" main.py --mode daily --cron >> logs\cron.log 2>&1
