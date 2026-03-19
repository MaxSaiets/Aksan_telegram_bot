@echo off
echo === Логи всіх сервісів (Ctrl+C щоб вийти) ===
docker compose logs -f --tail=100
