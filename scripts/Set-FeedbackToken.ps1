<#
.SYNOPSIS
Helper для шифрования PAT GitHub feedback-репо через Windows DPAPI.

.DESCRIPTION
До этого скрипта `~/.claude/.feedback-config.json` хранил PAT в plaintext —
если файл случайно попадал в репо / в логи / в чат-историю, токен утекал.

Этот скрипт:
1. Спрашивает PAT через Read-Host -AsSecureString (PAT не виден в истории
   PowerShell, не светится в screen recorder).
2. Шифрует через DPAPI CurrentUser scope. Расшифровать может **только**
   тот же Windows-пользователь на **той же машине** (DPAPI key derived
   от user login credentials).
3. Записывает в .feedback-config.json поле `token_encrypted`, обнуляет
   старое поле `token` (если было).

Запустить руками (НЕ из hook'ов):

    & "$env:USERPROFILE\.claude\scripts\Set-FeedbackToken.ps1"

После — feedback-collector.ps1 автоматически подхватит token_encrypted
(см. блок Decrypt в начале collector'а).

При переустановке Windows / переносе на другой ПК / смене user'а —
запустить этот скрипт заново. DPAPI ключ привязан к user+machine.

.NOTES
DPAPI CurrentUser scope:
- Encrypted blob может расшифровать ТОЛЬКО тот же user на той же машине.
- Защищает от: утечки .feedback-config.json в git, копирования на чужой ПК.
- НЕ защищает от: malware работающего под этим же user (нет защиты от
  локального атакующего с админом — что приемлемо для feedback-PAT).
#>

$ErrorActionPreference = 'Stop'

$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$ConfigFile = Join-Path $ClaudeDir '.feedback-config.json'

Write-Host ""
Write-Host "=== Set-FeedbackToken: шифрование PAT через DPAPI ===" -ForegroundColor Cyan
Write-Host ""

# 1. Загрузить существующий конфиг (или создать пустой)
if (Test-Path $ConfigFile) {
    try {
        $cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Host "Найден существующий $($ConfigFile)" -ForegroundColor Green
    } catch {
        Write-Host "WARN: существующий .feedback-config.json не парсится как JSON: $_" -ForegroundColor Yellow
        Write-Host "Создаю новый конфиг." -ForegroundColor Yellow
        $cfg = [PSCustomObject]@{}
    }
} else {
    Write-Host "Файла нет, создам новый: $ConfigFile" -ForegroundColor Yellow
    $cfg = [PSCustomObject]@{}
}

# 2. Спросить github_repo если его нет
if (-not $cfg.github_repo) {
    $defaultRepo = "K7-LS/claude-base-feedback"
    $repo = Read-Host "GitHub repo для feedback (default: $defaultRepo)"
    if (-not $repo) { $repo = $defaultRepo }
    $cfg | Add-Member -NotePropertyName 'github_repo' -NotePropertyValue $repo -Force
}

Write-Host ""
Write-Host "GitHub repo: $($cfg.github_repo)" -ForegroundColor Cyan

# 3. Спросить PAT через SecureString (PAT не виден в history)
Write-Host ""
Write-Host "Введи GitHub Personal Access Token (PAT с repo scope)." -ForegroundColor Cyan
Write-Host "Ввод СКРЫТ (Read-Host -AsSecureString). Никуда не пишется кроме encrypted поля." -ForegroundColor Gray
$securePat = Read-Host "PAT" -AsSecureString

if ($securePat.Length -eq 0) {
    Write-Host "ERROR: пустой PAT. Прерывание." -ForegroundColor Red
    exit 1
}

# 4. Зашифровать через DPAPI CurrentUser (default scope для ConvertFrom-SecureString)
try {
    $encrypted = ConvertFrom-SecureString -SecureString $securePat
} catch {
    Write-Host "ERROR: не удалось зашифровать через DPAPI: $_" -ForegroundColor Red
    exit 1
}

# 5. Записать в конфиг, обнулить plain token
$cfg | Add-Member -NotePropertyName 'token_encrypted' -NotePropertyValue $encrypted -Force
if ($cfg.PSObject.Properties.Name -contains 'token') {
    Write-Host ""
    Write-Host "Обнаружено старое поле 'token' (plaintext) — обнуляю." -ForegroundColor Yellow
    $cfg.token = $null
}

# 6. Сохранить
$json = $cfg | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($ConfigFile, $json, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "OK. PAT зашифрован и записан в $ConfigFile" -ForegroundColor Green
Write-Host ""
Write-Host "Проверь что feedback-collector.ps1 работает с новым форматом:" -ForegroundColor Cyan
Write-Host "    & `"`$env:USERPROFILE\.claude\scripts\feedback-collector.ps1`"" -ForegroundColor Gray
Write-Host ""
Write-Host "При переустановке Windows / переносе на другой ПК — запустить этот скрипт заново." -ForegroundColor Yellow
