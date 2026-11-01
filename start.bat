@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Polina English Studio
echo Откройте http://127.0.0.1:8088
echo Пароли первого входа: data\first-login.txt
python server.py
pause
