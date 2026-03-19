# Project Context

This file is the compact architecture and operations reference for the project.

## Purpose

The bot is used to:
- accept product videos from Telegram
- upload original videos to YouTube
- create processed videos with overlay text
- forward processed media to a target Telegram group
- accept and compress multiple photos into lightweight JPG files
- generate export files for Rozetka and the website

## Main runtime mode

The recommended runtime is polling, not webhook.

Why:
- Windows server environment
- historically `ngrok + webhook` was unstable
- polling is simpler and more reliable for this project

Main runtime entry:
- [polling.py](H:\AKSAN\telegram_aksan_bot\_publish\polling.py)

## Core flows

### 1. Video flow
User flow:
1. press `📤 Відправити відео`
2. send a video with caption
3. bot validates caption
4. Celery task starts
5. original video goes to YouTube
6. overlay video goes to target Telegram group

Task file:
- [app/tasks/video_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\video_pipeline.py)

Current important rules:
- caption is mandatory
- if caption is missing, bot replies `Напишіть назву.`
- video pipeline does not perform fuzzy matching anymore
- video pipeline does not search catalog/model data at upload time
- final response should not contain fuzzy strategy or Rozetka lookup text

### 2. Photo flow
User flow:
1. press `📸 Додати фото`
2. send one or multiple photos or image documents
3. send code in separate message
4. bot compresses photos and sends JPGs to target group

Task file:
- [app/tasks/photo_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\photo_pipeline.py)

Important rules:
- photos convert to JPG
- max bounding size is `600x900`
- there is a cancel button and delete-last-photo-batch button

### 3. Undo flow
User flow:
1. press `↩️ Скасувати останнє відео`
2. confirm deletion
3. bot deletes latest processed video

Task file:
- [app/tasks/undo_task.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\undo_task.py)

Important rules:
- YouTube deletion must work for standard watch URLs and other supported YouTube URL formats
- if products rows do not exist, cleanup falls back to parsed model code from caption

### 4. File generation flow
Task file:
- [app/tasks/files_task.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\files_task.py)

Generator file:
- [app/services/files_generator.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\files_generator.py)

Current design:
- file generation uses YouTube titles plus Rozetka variants
- matching is exact by model/category parsing, not fuzzy text
- one latest YouTube video is used per `(model, category)` pair
- output is distributed to all matching Rozetka/site variants for allowed size groups

## SKU parsing rules

Source file:
- [app/services/sku_parser.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\sku_parser.py)

Extracted from video title:
- model code
- category: `норма`, `ботал`, `супер ботал`

Variant size groups:
- `норма`: `40`, `42`, `44`
- `норма` may include `46` if `42/44` exist and `40` does not
- `ботал`: `50`, `52`, `54`
- `супер ботал`: `56`, `58`, `60`

Important principle:
- no fuzzy text strategy
- full exact matching only

## Telegram layer

Main user-facing file:
- [app/telegram/router.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\router.py)

Buttons:
- [app/telegram/keyboard.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\keyboard.py)

Important recent fix:
- router texts were rewritten to clean UTF-8 after mojibake issues in `/start` and other messages

## External integrations

### Telegram Bot API
- intake from private chat
- send processed video/photo results to target group
- send status/progress messages to user

### Telegram MTProto / Telethon
- fallback for downloading larger files when Bot API limits are hit

### YouTube
- upload originals
- delete videos in undo flow

### Rozetka
- used when generating export files

### SalesDrive
- still present in project, but current upload-time video pipeline should not depend on catalog lookup there

### Supabase
- used by client/database layer already configured in project

## Storage and temp files

Main temp folder:
- [tmp](H:\AKSAN\telegram_aksan_bot\_publish\tmp)

Examples:
- temporary videos
- logs
- exported tracking files for Rozetka/site

## Known operational constraints

1. Windows paths with Cyrillic caused repeated issues
- server deploy path is normalized through `C:\bots\telegram_aksan_bot`
- this may be a junction to the real Desktop path

2. Deploy notifications are sent through Python bot code
- file: [app/services/deploy_notify.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\deploy_notify.py)
- avoids fragile direct PowerShell Telegram calls

3. The repo contains some old mojibake comments in non-critical files
- if touching such files, rewrite in UTF-8 instead of patching line-by-line when possible

4. `ngrok.exe` is still present in repo folder
- polling is preferred
- webhook mode is not the recommended production path

## Fast orientation checklist

If you return to this project later, read in this order:
1. [README.md](H:\AKSAN\telegram_aksan_bot\_publish\README.md)
2. [docs/CI_CD.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\CI_CD.md)
3. [docs/LLM_HANDOFF.md](H:\AKSAN\telegram_aksan_bot\_publish\docs\LLM_HANDOFF.md)
4. [app/telegram/router.py](H:\AKSAN\telegram_aksan_bot\_publish\app\telegram\router.py)
5. [app/tasks/video_pipeline.py](H:\AKSAN\telegram_aksan_bot\_publish\app\tasks\video_pipeline.py)
6. [app/services/files_generator.py](H:\AKSAN\telegram_aksan_bot\_publish\app\services\files_generator.py)
