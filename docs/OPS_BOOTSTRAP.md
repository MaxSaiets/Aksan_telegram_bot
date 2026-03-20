# Ops Bootstrap

This is the quick bootstrap reference for Codex-specific project intelligence.

## Canonical Repo
- [H:\AKSAN\telegram_aksan_bot\_publish](H:\AKSAN\telegram_aksan_bot\_publish)
- repo-local agent rules: [AGENTS.md](H:\AKSAN\telegram_aksan_bot\_publish\AGENTS.md)

## Codex Global Config
- Codex config file: `C:\Users\sayet\.codex\config.toml`
- custom global skills root: `C:\Users\sayet\.codex\skills\`

## Global Skills Added For This Project Stack
- `python-fastapi-celery`
- `windows-service-ops`
- `supabase-safe-ops`
- `github-actions-cicd`
- `aksan-telegram-bot`

## MCP Servers Expected
- `openaiDeveloperDocs`
- `playwright`
- `github`
- `supabase`

## Fast Verification
### Check repo-local AGENTS file
```powershell
dir H:\AKSAN\telegram_aksan_bot\_publish\AGENTS.md
```

### Check global skills
```powershell
Get-ChildItem C:\Users\sayet\.codex\skills
```

### Check Codex config
```powershell
Get-Content C:\Users\sayet\.codex\config.toml
```

### Check Playwright runner command exists
```powershell
& "C:\Program Files\nodejs\npx.cmd" --version
```

## Notes
- The GitHub and Supabase MCP entries may still require authentication the first time they are used.
- The repo docs remain the source of truth. Skills and AGENTS orchestrate how Codex should use those docs, not replace them.
- Production deploy still runs through GitHub Actions + self-hosted Windows runner.
