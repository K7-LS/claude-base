<#
.SYNOPSIS
Вливает settings.shared.json → settings.json без перезаписи UI-driven полей.

.DESCRIPTION
Архитектура (token-economy v2, 2026-07-26):

  settings.shared.json  — shared между всеми ПК через git. Содержит
                          только язык и односторонние sync-hooks.

  settings.json         — personal, gitignored. Сюда Claude Code UI пишет
                          theme, reasoning/effort, plugins, model и т.п.

Логика merge:

1. Если ключ есть в shared но НЕТ в personal — добавляем (новый shared key).
2. Для `language` и `hooks` shared побеждает.
3. Если ключ есть только в personal — оставляем (UI-driven: theme, viewMode
   и т.п.).
4. Ключ `_comment` и `_added` из shared игнорируем (только метаинформация).
5. Один раз удаляем ранее принудительные expensive-ключи из
   `_retired_shared_keys`; после миграции пользователь может задать их лично.

Запуск:
  powershell -File scripts/merge-shared-settings.ps1

Идемпотентен: повторный запуск без изменений в shared = no-op.

Возвращает exit 0 при успехе, exit 1 если settings.shared.json невалиден.
#>

$ErrorActionPreference = 'Stop'

$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$SharedFile = Join-Path $ClaudeDir 'settings.shared.json'
$PersonalFile = Join-Path $ClaudeDir 'settings.json'
$LogFile = Join-Path $ClaudeDir 'auto-sync.log'
$MigrationMarker = Join-Path $ClaudeDir '.local-state\shared-settings-v2-migrated.flag'

function Write-MergeLog { param($msg)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] merge-shared-settings: $msg" |
        Add-Content -Path $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
}

if (-not (Test-Path $SharedFile)) {
    Write-MergeLog "skip: $SharedFile not found"
    exit 0
}

# Read shared
try {
    $shared = Get-Content $SharedFile -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-MergeLog "FAILED: settings.shared.json invalid JSON: $_"
    exit 1
}

# Read personal (or create empty if missing)
if (Test-Path $PersonalFile) {
    try {
        $personal = Get-Content $PersonalFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-MergeLog "WARN: settings.json invalid — recreating from shared"
        $personal = [PSCustomObject]@{}
    }
} else {
    Write-MergeLog "personal settings.json missing — creating from shared"
    $personal = [PSCustomObject]@{}
}

# Strictly-shared keys (всегда побеждают значение shared)
$SharedKeys = @('language', 'hooks')

# Meta keys to skip: любой ключ с префиксом "_" — комментарий/метаинформация
$changed = $false
$retirementPending = -not (Test-Path $MigrationMarker)
$retiredKeys = @($shared._retired_shared_keys)
if ($retirementPending) {
    foreach ($key in $retiredKeys) {
        if ($key -and ($personal.PSObject.Properties.Name -contains $key)) {
            $personal.PSObject.Properties.Remove([string]$key)
            Write-MergeLog "retired formerly shared key: $key"
            $changed = $true
        }
    }
}

foreach ($prop in $shared.PSObject.Properties) {
    $key = $prop.Name
    if ($key.StartsWith('_')) { continue }

    $sharedValue = $prop.Value
    $personalHasKey = $personal.PSObject.Properties.Name -contains $key

    if ($SharedKeys -contains $key) {
        # Strictly shared — overwrite
        $personalValue = if ($personalHasKey) { $personal.$key } else { $null }
        $sharedJson = $sharedValue | ConvertTo-Json -Depth 20 -Compress
        $personalJson = if ($null -ne $personalValue) { $personalValue | ConvertTo-Json -Depth 20 -Compress } else { '' }
        if ($sharedJson -ne $personalJson) {
            if ($personalHasKey) {
                $personal.$key = $sharedValue
            } else {
                $personal | Add-Member -NotePropertyName $key -NotePropertyValue $sharedValue
            }
            Write-MergeLog "updated shared key: $key"
            $changed = $true
        }
    } elseif (-not $personalHasKey) {
        # Other keys from shared — only add if missing in personal
        $personal | Add-Member -NotePropertyName $key -NotePropertyValue $sharedValue
        Write-MergeLog "added new key: $key"
        $changed = $true
    }
    # else: personal already has non-shared key — keep as is (UI-driven)
}

if ($changed) {
    # Backup personal before overwrite (one slot, overwritten on each merge)
    $backup = "$PersonalFile.bak"
    if (Test-Path $PersonalFile) {
        Copy-Item $PersonalFile $backup -Force
    }
    # Save merged personal — UTF-8 без BOM (Claude Code expects это)
    $json = $personal | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($PersonalFile, $json, [System.Text.UTF8Encoding]::new($false))
    Write-MergeLog "merged shared → personal (backup at $backup)"
} else {
    Write-MergeLog "no changes — already in sync"
}

if ($retirementPending) {
    $markerDir = Split-Path -Parent $MigrationMarker
    if (-not (Test-Path $markerDir)) {
        New-Item -ItemType Directory -Path $markerDir -Force | Out-Null
    }
    Set-Content -LiteralPath $MigrationMarker -Value 'token-economy-v2' -Encoding ASCII
    Write-MergeLog "legacy forced settings retired; future personal choices are preserved"
}

exit 0
