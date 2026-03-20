## Canonical Workspace
- Work only in `H:\AKSAN\telegram_aksan_bot\_publish` for real changes.
- Treat `main` in the `_publish` repo as the source of truth.
- Treat `C:\bots\telegram_aksan_bot` as the canonical production deploy root on the Windows server.
- Do not use the older non-git root as the main working copy unless the user explicitly asks for server hotfix work.

## First Read Order
Before making non-trivial changes, read in this order:
1. `README.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/CI_CD.md`
4. `docs/LLM_HANDOFF.md`
5. `docs/OPS_BOOTSTRAP.md`
6. `app/telegram/router.py`
7. `app/tasks/video_pipeline.py`
8. `app/services/files_generator.py`
9. `app/services/sku_parser.py`

## Non-Negotiable Project Rules
- Prefer polling; do not treat webhook + ngrok as the default production path.
- Do not edit production server files directly when CI/CD is healthy.
- Keep exact matching only; do not reintroduce fuzzy matching unless the user explicitly requests it.
- Keep user-facing strings in clean UTF-8.
- For photos, preserve append-only metadata/history; do not overwrite prior batches.
- For videos, keep upload-time flow independent from catalog lookup; file generation handles matching/export logic.

## Execution Guardrails
- Read the relevant docs before modifying architecture, deploy logic, exports, or matching rules.
- Run focused tests before push; prefer the smallest useful pytest subset.
- When production issues appear, check in this order: GitHub Actions `Deploy Bot`, deployed commit, `aksan_bot_polling`, `aksan_bot_worker`, `.env`, then manual runtime.
- Always use the OpenAI developer documentation MCP server if you need to work with the OpenAI API, ChatGPT Apps SDK, Codex, or related docs without me having to explicitly ask.

## Skills Routing
- If the task is about FastAPI + worker + Telegram bot orchestration, use `$python-fastapi-celery`.
- If the task is about Windows services, NSSM, runner accounts, or deploy recovery, use `$windows-service-ops`.
- If the task is about Supabase schema/data/API work, use `$supabase-safe-ops`.
- If the task is about GitHub Actions, self-hosted runner failures, or deploy workflow debugging, use `$github-actions-cicd`.
- If the task is specifically about this bot's business rules, media flows, export logic, or Telegram UX, use `$aksan-telegram-bot`.

## MCP Routing
- Use `openaiDeveloperDocs` for OpenAI, Codex, and OpenAI API documentation.
- Use `playwright` for browser automation, website/API smoke checks, and UI verification.
- Use `github` for repository, PR, issue, and Actions intelligence.
- Use `supabase` for Supabase schema, data, and project inspection.

## High-Signal Commands
```powershell
python -m pytest tests\test_webhook.py
python -m pytest tests\test_photo_pipeline.py tests\test_photo_library.py tests\test_webhook.py
Get-Service aksan_bot_polling, aksan_bot_worker
git rev-parse --short HEAD
.\deploy.ps1
```
