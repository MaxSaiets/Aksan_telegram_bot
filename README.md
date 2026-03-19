# Aksan Telegram Bot

Telegram bot for:

- video intake and processing
- multi-photo intake with JPG compression
- export/file generation tasks
- sending results to a target Telegram group

## Local run

1. Create `.env` from `.env.example`.
2. Install dependencies from `requirements.txt`.
3. Run Redis.
4. Start the bot:

```powershell
python polling.py
```

5. Start the worker:

```powershell
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

## Windows server deploy

Recommended production setup:

- `Memurai` for Redis
- `FFmpeg`
- `NSSM` services:
  - `aksan_bot_polling`
  - `aksan_bot_worker`
- GitHub Actions self-hosted runner for CI/CD

## CI/CD

Push changes to `main`. The self-hosted GitHub runner on the server will:

1. pull the latest code
2. install/update Python packages
3. restart the bot services
