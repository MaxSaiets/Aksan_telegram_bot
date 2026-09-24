Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot

if (-not (Test-Path $projectRoot)) {
    throw "Project root not found: $projectRoot"
}

$pythonExe = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    throw "Python venv executable not found: $pythonExe"
}

Set-Location $projectRoot

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    Write-Host "Deploy step: $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Set-EnvFileValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return
    }

    $lines = if (Test-Path $Path) { [System.IO.File]::ReadAllLines($Path) } else { @() }
    $prefix = "$Name="
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $found = $true
            "$Name=$Value"
        } else {
            $line
        }
    }
    if (-not $found) {
        $updated += "$Name=$Value"
    }

    # Keep secrets out of logs and out of Git; .env is ignored by design.
    [System.IO.File]::WriteAllLines($Path, [string[]]$updated, [System.Text.UTF8Encoding]::new($false))
}

try {
    Set-EnvFileValue -Path (Join-Path $projectRoot '.env') -Name 'GEMINI_API_KEY' -Value $env:GEMINI_API_KEY
} catch {
    # Deployment must still recover the bot when the runner cannot edit the protected .env file.
    Write-Warning "Could not update GEMINI_API_KEY in .env; keeping the server value unchanged."
}

Invoke-CheckedCommand -Name 'git remote configuration' -Command {
    & git -c "safe.directory=$projectRoot" remote set-url origin https://github.com/MaxSaiets/Aksan_telegram_bot.git
}
Invoke-CheckedCommand -Name 'git fetch' -Command {
    & git -c "safe.directory=$projectRoot" fetch origin
}
Invoke-CheckedCommand -Name 'git reset' -Command {
    & git -c "safe.directory=$projectRoot" reset --hard origin/main
}

$shortSha = (& git -c "safe.directory=$projectRoot" rev-parse --short HEAD).Trim()

Invoke-CheckedCommand -Name 'pip upgrade' -Command { & $pythonExe -m pip install --upgrade pip }
Invoke-CheckedCommand -Name 'requirements installation' -Command { & $pythonExe -m pip install -r requirements.txt }
Invoke-CheckedCommand -Name 'optional dependency installation' -Command { & $pythonExe -m pip install telethon cryptg }

Restart-Service aksan_bot_polling
Restart-Service aksan_bot_worker
& $pythonExe -m app.services.deploy_notify $shortSha

Write-Host "Deploy completed successfully for $projectRoot."
