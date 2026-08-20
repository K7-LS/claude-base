<#
.SYNOPSIS
Скрипт для Daniil'а — забрать новый feedback со всех веток
claude-base-feedback репо в локальный обзор.

.DESCRIPTION
Запускается на DANIILPC периодически (раз в день/неделю).
Workflow:

1. Клонирует/обновляет ~/.claude/feedback-inbox/ от claude-base-feedback.
2. Fetch всех branches feedback/*.
3. Для каждой ветки — checkout и копирование новых файлов в
   `~/.claude/feedback-inbox/all/<branch>/<filename>.md`.
4. Список новых файлов выводит в консоль для review.

Конфиг — `~/.claude/.feedback-config.json` (тот же что у consumers, но
с правом read+admin на feedback-репо):
{
  "github_repo": "K7-LS/claude-base-feedback",
  "token": "ghp_..."
}

Использование:
  powershell -File ~/.claude/scripts/pull-feedback.ps1

После review Daniil решает что внедрять в shared базу и руками
коммитит в claude-base main.
#>

# PowerShell 5.1 ловушка: `2>&1 | Out-Null` на native git заворачивает
# stderr-строки в ErrorRecord (NativeCommandError) и валит script при
# $ErrorActionPreference='Stop' даже если git exit code = 0. Используем
# 'Continue' и явный `2>$null` для подавления stderr — это работает на
# обеих PS-edition без побочных эффектов.
$ErrorActionPreference = 'Continue'

$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$InboxDir = Join-Path $ClaudeDir 'feedback-inbox'
$ConfigFile = Join-Path $ClaudeDir '.feedback-config.json'

if (-not (Test-Path $ConfigFile)) {
    Write-Host "FAIL: $ConfigFile not found." -ForegroundColor Red
    Write-Host "Создай файл с {github_repo, token, token_encrypted}." -ForegroundColor Yellow
    exit 1
}

$cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $cfg.github_repo) {
    Write-Host "FAIL: .feedback-config.json missing github_repo" -ForegroundColor Red
    exit 1
}

# === DPAPI decrypt (2026-05-27) ===
# Конфиг хранит PAT в одном из двух форматов:
#   - token_encrypted: зашифрован через scripts/Set-FeedbackToken.ps1 (DPAPI
#     CurrentUser scope). Расшифровать может только тот же Windows-user на
#     той же машине — защита от утечки .feedback-config.json в логи/чат.
#   - token: legacy plaintext (оставлен для backward compat пока сотрудники
#     не мигрировали через Set-FeedbackToken.ps1).
# Логика идентична feedback-collector.ps1 — синхронизированы.
$token = $null
if ($cfg.token_encrypted) {
    try {
        $secStr = ConvertTo-SecureString -String $cfg.token_encrypted -ErrorAction Stop
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secStr)
        $token = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    } catch {
        Write-Host "FAIL: token_encrypted не расшифровывается (другой user/machine?)." -ForegroundColor Red
        Write-Host "Запустить scripts/Set-FeedbackToken.ps1 на этом ПК." -ForegroundColor Yellow
        exit 1
    }
} elseif ($cfg.token) {
    Write-Host "WARN: .feedback-config.json использует plain token (legacy). Запустить scripts/Set-FeedbackToken.ps1 для шифрования через DPAPI." -ForegroundColor Yellow
    $token = $cfg.token
} else {
    Write-Host "FAIL: .feedback-config.json missing both token_encrypted and token" -ForegroundColor Red
    exit 1
}

$repo = $cfg.github_repo

# Clone repo if missing, else fetch
$repoUrl = "https://${token}@github.com/${repo}.git"
$repoLocal = Join-Path $InboxDir '.repo'

if (-not (Test-Path $repoLocal)) {
    Write-Host "Clone $repo to $repoLocal..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $InboxDir -Force | Out-Null
    & git clone $repoUrl $repoLocal 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: git clone exit=$LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Fetch updates for $repo..." -ForegroundColor Cyan
    Push-Location $repoLocal
    & git fetch --all --prune 2>$null
    Pop-Location
}

# Перечень feedback/* веток
Push-Location $repoLocal
$branches = & git branch -r 2>$null | Where-Object { $_ -match 'origin/feedback/' } | ForEach-Object { ($_ -replace 'origin/', '').Trim() }
Pop-Location

if (-not $branches) {
    Write-Host "Нет feedback/* веток в репо." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "=== Найдено $($branches.Count) ветка(ок) feedback ===" -ForegroundColor Green
foreach ($branch in $branches) {
    Write-Host ""
    Write-Host "--- $branch ---" -ForegroundColor Cyan
    # PS 5.1: Join-Path принимает 2 параметра (Path + ChildPath). На PS 7+
    # допустимы 3+. Используем nested Join-Path для совместимости с обеими
    # editions — на этой машине Windows PowerShell 5.1 по умолчанию.
    $branchOutDir = Join-Path (Join-Path $InboxDir 'all') ($branch -replace '/', '_')
    New-Item -ItemType Directory -Path $branchOutDir -Force | Out-Null

    Push-Location $repoLocal
    & git checkout -q $branch 2>$null

    # Скопировать всё из feedback/ в branchOutDir
    $feedbackPath = Join-Path $repoLocal 'feedback'
    if (Test-Path $feedbackPath) {
        # smoke-заглушки инсталлера не тащим в обзор (Блок 4, 2026-07-07):
        # это тех-файлы проверки апдейтера, разбирать в них нечего
        $files = Get-ChildItem $feedbackPath -File -Filter '*.md' |
            Where-Object { $_.Name -notmatch 'updater-smoke-test|smoke-test-after-pat-fix|smoke-test-deliseevpc' }
        foreach ($f in $files) {
            $dest = Join-Path $branchOutDir $f.Name
            $isNew = -not (Test-Path $dest)
            Copy-Item $f.FullName $dest -Force
            $mark = if ($isNew) { '[NEW]' } else { '[upd]' }
            Write-Host "  $mark $($f.Name)" -ForegroundColor $(if ($isNew) { 'Green' } else { 'Gray' })
        }
    } else {
        Write-Host "  (нет feedback/ папки в ветке)" -ForegroundColor DarkGray
    }
    Pop-Location
}

Push-Location $repoLocal
& git checkout -q main 2>$null
Pop-Location

Write-Host ""
Write-Host "=== Готово. Все feedback файлы в $InboxDir\all\ ===" -ForegroundColor Green
Write-Host "Ревью: открыть нужный файл, решить что внедрять в shared базу." -ForegroundColor Yellow
