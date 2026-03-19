# LLM Handoff

This file is optimized for future AI agents or fresh-context sessions.
It is intentionally direct and operational.

## Canonical workspace

Use this repository for real work:
- [H:\AKSAN\telegram_aksan_bot\_publish](H:\AKSAN\telegram_aksan_bot\_publish)

Do not use the older non-git working folder as the main source of truth.
The `_publish` folder is the standalone git repo connected to GitHub.

## Canonical branch

- `main`

## Canonical remote behavior

- local edits happen in `_publish`
- pushes to `main` trigger production deploy through GitHub Actions self-hosted runner

## First files to read after context reset

1. [README.md](H:\AKSAN\telegram_aksan_bot\_publish\README.md)
2. [docs/PROJECT_CONTEXT.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\PROJECT_CONTEXT.md)
3. [docs/CI_CD.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\CI_CD.md)
4. [app/telegram/router.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\router.py)
5. [app/tasks/video_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\video_pipeline.py)
6. [app/services/files_generator.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\files_generator.py)
7. [app/services/sku_parser.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\sku_parser.py)

## Current business behavior

### Video flow
- user must press send-video button
- caption is required
- no caption => reply `Напишіть назву.`
- upload-time pipeline does not do fuzzy product matching anymore
- upload-time pipeline does not append catalog matching summary to the final success message
- undo flow should remove the previous YouTube video and clean exported mappings

### Photo flow
- user can upload multiple photos
- can upload as photo or image document
- sends code separately
- bot converts output to JPG and compresses/resizes within `600x900`

### File generation
- file generation is the place where title parsing and SKU/category logic matter
- exact matching only
- no fuzzy_text strategy
- title parser should detect model code and category (`норма`, `ботал`, `супер ботал`)
- Rozetka and site exports should distribute the latest video to all matching variants/colors within allowed size groups

## Size rules
- `норма`: `40`, `42`, `44`
- `норма` may include `46` if `42/44` exist but `40` does not
- `ботал`: `50`, `52`, `54`
- `супер ботал`: `56`, `58`, `60`

## Important code locations

### Telegram UX
- [app/telegram/router.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\router.py)
- [app/telegram/keyboard.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\keyboard.py)

### Media processing
- [app/tasks/video_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\video_pipeline.py)
- [app/tasks/photo_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\photo_pipeline.py)
- [app/services/video_editor.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\video_editor.py)
- [app/services/photo_processor.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\photo_processor.py)

### Matching and exports
- [app/services/sku_parser.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\sku_parser.py)
- [app/services/model_matcher.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\model_matcher.py)
- [app/services/files_generator.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\files_generator.py)
- [app/services/youtube_catalog.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\youtube_catalog.py)

### Deploy/ops
- [deploy.ps1](H:\AKSAN\telegram_aksan_bot\_publish\deploy.ps1)
- [.github/workflows/deploy.yml](H:\AKSAN\telegram_aksan_bot\_publish\.github\workflows\deploy.yml)
- [app/services/deploy_notify.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\deploy_notify.py)

## Operational truth about the server

Production server uses a Windows path alias:
- logical path: `C:\bots\telegram_aksan_bot`

This is the path CI/CD uses and should be treated as the deploy root.

## How to work safely

1. Prefer editing `_publish`, not ad-hoc server files.
2. Prefer whole-file UTF-8 rewrites when a file contains mojibake or mixed encodings.
3. Run focused tests before push.
4. Keep user-facing strings in UTF-8.
5. Avoid reintroducing fuzzy matching unless explicitly requested.
6. Do not move deploy back to webhook/ngrok mode without a clear reason.

## Useful test commands

```powershell
python -m pytest tests\test_webhook.py
python -m pytest tests\test_pipeline.py tests\test_sku_parser.py tests\test_webhook.py
python -m pytest tests\test_deploy_notify.py tests\test_webhook.py
```

## Things that have broken before

- mojibake in router strings
- server venv copied from another PC and became invalid
- GitHub runner permissions under Windows service account
- SSH host key issues in service context
- direct PowerShell Telegram notification path being unreliable

## If the bot suddenly stops responding

Check:
1. GitHub Actions latest deploy status
2. server current commit
3. `aksan_bot_polling` and `aksan_bot_worker` services
4. `.env` validity
5. ability to run polling manually
6. ability to run deploy notification manually

## If you need to verify deploy notification

Server command:
```powershell
cd C:\bots\telegram_aksan_bot
.\venv\Scripts\python.exe -m app.services.deploy_notify test123
```

Expected Telegram message:
- `Я оновився. Commit: test123`

## Commit style suggestion

Use small, specific commits such as:
- `Fix Telegram router text encoding`
- `Refactor video matching and file generation`
- `Use project sender for deploy notifications`

This makes recovery and future analysis much easier.
