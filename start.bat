@echo off
cd /d H:\AKSAN\telegram_aksan_bot

echo [1/2] Запуск ngrok...
start "ngrok" /MIN cmd /c "ngrok.exe http 8000 --domain=unsulphurized-unmakable-luci.ngrok-free.dev"
timeout /t 5 /nobreak >nul

echo [2/2] Запуск Docker...
docker compose up -d --build

echo.
echo === Бот запущено ===
echo Health: http://localhost:8000/health
echo Flower: http://localhost:5555
echo.
pause
