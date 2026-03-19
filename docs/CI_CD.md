# CI/CD and Server Operations

This document explains how the project is deployed and how the production server is expected to behave.

## Deployment model

The project uses:
- GitHub repository as the source of truth
- GitHub Actions workflow
- self-hosted GitHub runner on the Windows server
- polling mode for the bot
- Celery worker for background tasks

Main workflow file:
- [/.github/workflows/deploy.yml](H:\AKSAN\telegram_aksan_bot\_publish\.github\workflows\deploy.yml)

Deploy script:
- [/deploy.ps1](H:\AKSAN\telegram_aksan_bot\_publish\deploy.ps1)

## Server layout

Logical deploy path:
- `C:\bots\telegram_aksan_bot`

This path may be a junction pointing to the actual project directory on Desktop.
The logical path should be treated as canonical for deploy operations.

## Required server software

Windows server should have:
- Python 3.11
- FFmpeg available in `PATH`
- Memurai or Redis-compatible service
- project `venv`
- GitHub Actions self-hosted runner
- NSSM services for the bot and worker

## Required Windows services

Expected services:
- `aksan_bot_polling`
- `aksan_bot_worker`

These services should point to the project under `C:\bots\telegram_aksan_bot`.

## GitHub Actions flow

When a push goes to `main`:
1. GitHub starts `Deploy Bot`
2. self-hosted runner executes workflow on the server
3. workflow enters `C:\bots\telegram_aksan_bot`
4. workflow runs `deploy.ps1`
5. `deploy.ps1`:
   - marks repo as safe for git
   - sets remote to GitHub HTTPS URL
   - fetches latest code
   - hard-resets to `origin/main`
   - updates Python packages
   - restarts `aksan_bot_polling`
   - restarts `aksan_bot_worker`
   - sends deploy notification to Telegram

## Why HTTPS is used on the server

The project previously had repeated SSH host key and permission issues under service accounts on Windows.
For the runner, HTTPS is simpler and more stable because it only needs fetch/reset behavior from a public repository.

Local development may still use another auth strategy, but server deploy should stay on HTTPS unless there is a strong reason to change it.

## Deploy notification

Source file:
- [app/services/deploy_notify.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\deploy_notify.py)

Behavior:
- after successful deploy, server runs Python notification module
- notification goes to `DEPLOY_NOTIFY_CHAT_ID` if configured
- otherwise first `TELEGRAM_ALLOWED_USERS` value is used

Expected message:
- `Я оновився. Commit: <short_sha>`

## Important `.env` keys for operations

Minimum keys relevant to deploy/runtime:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_TARGET_CHAT_ID`
- `TELEGRAM_ALLOWED_USERS`
- `DEPLOY_NOTIFY_CHAT_ID`
- `REDIS_URL`
- `USE_MOCKS=false`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

## Manual verification commands on the server

### Verify current deployed commit
```powershell
cd C:\bots\telegram_aksan_bot
git rev-parse --short HEAD
```

### Verify deploy notification module exists
```powershell
dir C:\bots\telegram_aksan_bot\app\services\deploy_notify.py
```

### Run deploy notification manually
```powershell
cd C:\bots\telegram_aksan_bot
.\venv\Scripts\python.exe -m app.services.deploy_notify test123
```

### Run deploy manually
```powershell
cd C:\bots\telegram_aksan_bot
.\deploy.ps1
```

### Check services
```powershell
Get-Service aksan_bot_polling, aksan_bot_worker
```

### Restart services
```powershell
Restart-Service aksan_bot_polling
Restart-Service aksan_bot_worker
```

## When deploy succeeds but bot does not respond

Check in this order:
1. `Get-Service aksan_bot_polling, aksan_bot_worker`
2. verify latest commit on server
3. verify `.env`
4. run polling manually
5. run Celery worker manually
6. inspect logs under `tmp`

## Common failure patterns already encountered

1. Broken `venv` after copying project from another machine
- fix: rebuild `venv` on server itself

2. Runner service lacked permissions
- fix: run GitHub Actions runner service under a user account with required access

3. Git safe.directory issues on Windows service account
- fix was added to deploy script

4. SSH host verification under service account
- avoided by moving runner-side fetch to HTTPS

5. Cyrillic path and encoding problems
- use `C:\bots\telegram_aksan_bot` as deploy root
- save edited files in UTF-8

## Recommended change workflow

Normal workflow should be:
1. edit code locally in `_publish`
2. run tests locally
3. `git add .`
4. `git commit -m "..."`
5. `git push`
6. watch GitHub Actions `Deploy Bot`
7. verify bot behavior in Telegram

Avoid editing the production server code directly unless the CI/CD path itself is broken.
