@echo off
cd /d D:\AI-Content-Hub\admin-server
"C:\Users\carson\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8765
