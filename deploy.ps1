Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-EnvMap([string]$envPath) {
    $map = @{}
    if (-not (Test-Path $envPath)) {
        return $map
    }

    foreach ($line in Get-Content $envPath) {
        if (-not $line -or $line.Trim().StartsWith('#') -or -not $line.Contains('=')) {
            continue
        }

        $parts = $line.Split('=', 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($key) {
            $map[$key] = $value
        }
    }

    return $map
}

function Send-DeployNotification([string]$projectRoot) {
    try {
        $envMap = Get-EnvMap (Join-Path $projectRoot '.env')
        $token = $envMap['TELEGRAM_BOT_TOKEN']
        if (-not $token) {
            return
        }

        $chatId = $envMap['DEPLOY_NOTIFY_CHAT_ID']
        if (-not $chatId) {
            $allowedUsers = $envMap['TELEGRAM_ALLOWED_USERS']
            if ($allowedUsers) {
                $chatId = ($allowedUsers.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -First 1)
            }
        }

        if (-not $chatId) {
            return
        }

        $shortSha = (& git rev-parse --short HEAD).Trim()
        $message = "Я оновився. Commit: $shortSha"
        $uri = "https://api.telegram.org/bot$token/sendMessage"
        Invoke-RestMethod -Method Post -Uri $uri -Body @{ chat_id = $chatId; text = $message } | Out-Null
    } catch {
        Write-Warning "Deploy notification failed: $($_.Exception.Message)"
    }
}

$projectRoot = if ($env:DEPLOY_PROJECT_ROOT) {
    $env:DEPLOY_PROJECT_ROOT
} else {
    $PSScriptRoot
}

if (-not (Test-Path $projectRoot)) {
    throw "Project root not found: $projectRoot"
}

$pythonExe = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    throw "Python venv executable not found: $pythonExe"
}

Set-Location $projectRoot

git config --system --add safe.directory $projectRoot
git remote set-url origin https://github.com/MaxSaiets/Aksan_telegram_bot.git

git fetch origin
if ($LASTEXITCODE -ne 0) {
    throw 'git fetch failed'
}

git reset --hard origin/main
if ($LASTEXITCODE -ne 0) {
    throw 'git reset failed'
}

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r requirements.txt
& $pythonExe -m pip install telethon cryptg

Restart-Service aksan_bot_polling
Restart-Service aksan_bot_worker
Send-DeployNotification $projectRoot

Write-Host "Deploy completed successfully for $projectRoot."
