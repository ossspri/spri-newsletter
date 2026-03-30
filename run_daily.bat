@echo off
chcp 65001 >nul
cd /d "C:\Users\martin.hs.yoo\내 드라이브\Apps\claude\newsletter_system"
"C:\Users\martin.hs.yoo\AppData\Local\Programs\Python\Python311\python.exe" main.py --mode daily >> logs\cron.log 2>&1
