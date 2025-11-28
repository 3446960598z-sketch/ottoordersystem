@echo off
start cmd /k "python manage.py runserver 127.0.0.1:8080"
timeout /t 2 /nobreak >nul
start http://127.0.0.1:8080/
pause