@echo off
echo === Реєстрація Telegram Webhook ===
docker compose exec web python scripts/register_webhook.py
pause
