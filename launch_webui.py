"""Web UI 런처 — 서버 시작 후 브라우저 자동 오픈."""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

project = Path(__file__).resolve().parent
python = sys.executable

proc = subprocess.Popen([python, str(project / "main.py"), "--mode", "server"])
time.sleep(8)
webbrowser.open("http://127.0.0.1:5000")
proc.wait()
