@echo off
chcp 65001 > nul
echo.
echo  Music Video Generator
echo  =====================
echo.

pip install -r requirements.txt --quiet

echo.
echo  正在启动服务器，浏览器将自动打开...
echo  按 Ctrl+C 停止
echo.

python app.py
pause
