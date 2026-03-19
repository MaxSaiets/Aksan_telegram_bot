@echo off
echo === Оновлення бота (git pull + rebuild) ===
git pull
docker compose down
docker compose up -d --build
echo.
echo Оновлено та запущено!
echo   Бот (API):  http://localhost:8000/health
echo   Моніторинг: http://localhost:5555
echo.
pause
