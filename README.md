# Aksan Telegram Bot

Telegram bot for processing product videos and photos, publishing processed media to a Telegram group, and generating export files for Rozetka and the website.

## What the bot does

The bot supports four main workflows:

1. Video intake
- user presses `📤 Відправити відео`
- sends a video with a caption
- bot downloads the file from Telegram
- uploads the original to YouTube
- creates an overlay version
- sends the processed video to the target Telegram group

2. Multi-photo intake
- user presses `📸 Додати фото`
- sends one or many photos, including image documents
- sends a code in a separate message
- bot compresses photos to JPG
- resizes them to fit within `600x900`
- sends the JPG files to the target Telegram group

3. Undo last video
- user presses `↩️ Скасувати останнє відео`
- bot removes the latest processed video from YouTube and local tracking

4. File generation
- user presses `📁 Отримати файли`
- bot generates files for Rozetka, the website, or a report task

## Current business rules

### Video handling
- video caption is required
- if a user sends a video without caption, bot replies: `Напишіть назву.`
- during video upload the bot no longer searches the catalog and no longer uses fuzzy matching
- catalog-style matching is deferred to file generation

### SKU and category parsing
Video titles are parsed for:
- model code
- category: `норма`, `ботал`, `супер ботал`

Matching is exact-only.

### Size groups
- `норма`: `40`, `42`, `44`
- `норма` may also include `46` if the model has `42/44` but no `40`
- `ботал`: `50`, `52`, `54`
- `супер ботал`: `56`, `58`, `60`

These rules are applied when generating export files from YouTube titles plus Rozetka variants.

## High-level architecture

Entry points:
- [main.py](H:\AKSAN\telegram_aksan_bot\_publish\main.py): FastAPI app and webhook endpoint
- [polling.py](H:\AKSAN\telegram_aksan_bot\_publish\polling.py): polling mode for stable Windows/server usage

Telegram layer:
- [app/telegram/router.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\router.py): user-facing handlers and state transitions
- [app/telegram/keyboard.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\keyboard.py): reply/inline keyboards
- [app/telegram/states.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\states.py): FSM states

Async work:
- [app/tasks/video_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\video_pipeline.py): full video pipeline
- [app/tasks/photo_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\photo_pipeline.py): photo pipeline
- [app/tasks/files_task.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\files_task.py): Rozetka/site file generation
- [app/tasks/undo_task.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\undo_task.py): undo last video
- [app/tasks/export_task.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\export_task.py): report/export flow

Service layer:
- [app/services/youtube_uploader.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\youtube_uploader.py)
- [app/services/video_editor.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\video_editor.py)
- [app/services/photo_processor.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\photo_processor.py)
- [app/services/files_generator.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\files_generator.py)
- [app/services/sku_parser.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\sku_parser.py)
- [app/services/telegram_sender.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\telegram_sender.py)
- [app/services/deploy_notify.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\deploy_notify.py)

Persistence:
- [app/database/videos_repo.py](H:\AKSAN\telegram_aksan_bot\_publish\app\database\videos_repo.py)
- [app/database/products_repo.py](H:\AKSAN\telegram_aksan_bot\_publish\app\database\products_repo.py)

## Local development

1. Create `.env` from [.env.example](H:\AKSAN\telegram_aksan_bot\_publish\.env.example)
2. Install dependencies
3. Run Redis or Memurai
4. Start the bot in polling mode
5. Start Celery worker

Commands:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install telethon cryptg
.\venv\Scripts\python.exe polling.py
```

Worker:

```powershell
.\venv\Scripts\celery.exe -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

## Tests

Main regression tests live in [tests](H:\AKSAN\telegram_aksan_bot\_publish\tests).

Useful commands:

```powershell
python -m pytest tests\test_webhook.py
python -m pytest tests\test_pipeline.py tests\test_sku_parser.py tests\test_webhook.py
python -m pytest tests\test_deploy_notify.py tests\test_webhook.py
```

## Deployment

Production notes are described in:
- [docs/CI_CD.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\CI_CD.md)
- [docs/PROJECT_CONTEXT.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\PROJECT_CONTEXT.md)
- [docs/LLM_HANDOFF.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\LLM_HANDOFF.md)
