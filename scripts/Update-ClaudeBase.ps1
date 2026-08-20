<#
.SYNOPSIS
Updater 2.0 — one-command setup + проверка claude-base на любом ПК команды.

.DESCRIPTION
Один скрипт делает всё что раньше было 8 ручных шагов:

  [1] Detect role (developer vs consumer по .developer-marker)
  [2] git pull origin main (с retry + bypass-proxy)
  [3] merge-shared-settings.ps1 (shared → personal settings.json)
  [4] verify-claude-base.ps1 (22 проверки)
  [5] Если consumer + нет .feedback-config.json — спросить PAT интерактивно
  [6] Если consumer + есть config — smoke-test push (создать тестовый feedback,
      проверить что прошёл через GitHub API)
  [7] Финальный summary с PASS/FAIL по каждому шагу
  [8] Если что-то упало — точная диагностика с командой для починки

Запуск:
  - Double-click `Update-ClaudeBase.bat` в проводнике (рекомендуется)
  - Либо: powershell -File "$HOME\.claude\scripts\Update-ClaudeBase.ps1"

Возвращает exit 0 если всё PASS, exit 1 если есть FAIL.
#>

$ErrorActionPreference = 'Continue'
$ClaudeDir = Join-Path $env:USERPROFILE '.claude'

$script:results = @()
function Record { param([string]$Step, [string]$Status, [string]$Detail = "")
    $script:results += [PSCustomObject]@{ Step = $Step; Status = $Status; Detail = $Detail }
}

function Section { param([string]$Title)
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

# ===================================================================
# Header
# ===================================================================
Write-Host ""
Write-Host "######################################################" -ForegroundColor Green
Write-Host "###  Update-ClaudeBase 2.0 — one-command setup     ###" -ForegroundColor Green
Write-Host "######################################################" -ForegroundColor Green
Write-Host ""
Write-Host "Host:    $env:COMPUTERNAME" -ForegroundColor Gray
Write-Host "User:    $env:USERNAME" -ForegroundColor Gray
Write-Host "Claude:  $ClaudeDir" -ForegroundColor Gray
Write-Host "Time:    $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# ===================================================================
# Step 1: Detect role
# ===================================================================
Section "1. Detect role"
$isDeveloper = Test-Path (Join-Path $ClaudeDir '.developer-marker')
if ($isDeveloper) {
    Write-Host "  Role: DEVELOPER (.developer-marker present)" -ForegroundColor Yellow
    Write-Host "  -> Будут пропущены шаги feedback-config + smoke-test (они только для consumer)." -ForegroundColor DarkGray
    Record "1. Role" "DEVELOPER"
} else {
    Write-Host "  Role: CONSUMER (no .developer-marker)" -ForegroundColor Green
    Record "1. Role" "CONSUMER"
}

# ===================================================================
# Step 2: Git pull
# ===================================================================
Section "2. Git pull origin main"
Push-Location $ClaudeDir
try {
    $output = & git -c http.proxy="" -c https.proxy="" pull --rebase --autostash origin main 2>&1
    $exit = $LASTEXITCODE
    $output | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    if ($exit -eq 0) {
        Write-Host "  [OK] git pull прошёл" -ForegroundColor Green
        Record "2. Git pull" "PASS"
    } else {
        Write-Host "  [FAIL] git pull exit=$exit" -ForegroundColor Red
        Record "2. Git pull" "FAIL" "exit=$exit"
    }
} catch {
    Write-Host "  [FAIL] exception: $_" -ForegroundColor Red
    Record "2. Git pull" "FAIL" "$_"
} finally {
    Pop-Location
}

# ===================================================================
# Step 3: Merge shared settings
# ===================================================================
Section "3. Merge shared settings → local settings.json"
$mergeScript = Join-Path $ClaudeDir 'scripts\merge-shared-settings.ps1'
if (-not (Test-Path $mergeScript)) {
    Write-Host "  [WARN] $mergeScript not found — pull прошёл частично?" -ForegroundColor Yellow
    Record "3. Merge settings" "WARN" "script not found"
} else {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $mergeScript 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] merge-shared-settings прошёл" -ForegroundColor Green
            Record "3. Merge settings" "PASS"
        } else {
            Write-Host "  [FAIL] merge exit=$LASTEXITCODE" -ForegroundColor Red
            Record "3. Merge settings" "FAIL" "exit=$LASTEXITCODE"
        }
    } catch {
        Write-Host "  [FAIL] exception: $_" -ForegroundColor Red
        Record "3. Merge settings" "FAIL" "$_"
    }
}

# ===================================================================
# Step 4: Verify
# ===================================================================
Section "4. Verify claude-base"
$verifyScript = Join-Path $ClaudeDir 'scripts\verify-claude-base.ps1'
if (-not (Test-Path $verifyScript)) {
    Write-Host "  [WARN] $verifyScript not found" -ForegroundColor Yellow
    Record "4. Verify" "WARN" "script not found"
} else {
    $verifyOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript 2>&1
    $verifyOutput | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -eq 0) {
        # Parse "=== Summary: N/M passed ===" line for an accurate count
        # instead of hard-coding (verify check list may grow).
        $summaryLine = $verifyOutput | Where-Object { $_ -match 'Summary:\s*(\d+/\d+)\s+passed' } | Select-Object -First 1
        $counts = if ($summaryLine -and $summaryLine -match 'Summary:\s*(\d+/\d+)\s+passed') { $matches[1] } else { 'all' }
        Record "4. Verify" "PASS" $counts
    } else {
        # Extract failed check names from verify output for summary
        $failedChecks = @($verifyOutput | Where-Object { $_ -match '\[FAIL\]\s+(.+)$' } | ForEach-Object {
            if ($_ -match '\[FAIL\]\s+(.+?)(\s+--.+)?$') { $matches[1].Trim() }
        })
        $detail = if ($failedChecks.Count -gt 0) {
            "failed: " + ($failedChecks -join '; ')
        } else {
            "see output above"
        }
        Record "4. Verify" "FAIL" $detail
    }
}

# ===================================================================
# Step 5/6: Consumer-only feedback setup
# ===================================================================
if (-not $isDeveloper) {
    Section "5. Feedback config (.feedback-config.json)"
    $configFile = Join-Path $ClaudeDir '.feedback-config.json'

    if (Test-Path $configFile) {
        try {
            $cfg = Get-Content $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($cfg.github_repo -and ($cfg.token_encrypted -or $cfg.token)) {
                $tokenForm = if ($cfg.token_encrypted) { 'token_encrypted (DPAPI)' } else { 'token (plaintext, legacy)' }
                Write-Host "  [OK] .feedback-config.json present, repo=$($cfg.github_repo), $tokenForm" -ForegroundColor Green
                if (-not $cfg.token_encrypted -and $cfg.token) {
                    Write-Host "  [WARN] plain token (legacy) — запусти scripts/Set-FeedbackToken.ps1 для DPAPI-шифрования." -ForegroundColor Yellow
                }
                Record "5. Feedback config" "PASS"
            } else {
                Write-Host "  [FAIL] config missing github_repo or token/token_encrypted" -ForegroundColor Red
                Record "5. Feedback config" "FAIL" "missing github_repo or token/token_encrypted"
            }
        } catch {
            Write-Host "  [FAIL] .feedback-config.json invalid JSON: $_" -ForegroundColor Red
            Record "5. Feedback config" "FAIL" "invalid JSON"
        }
    } else {
        Write-Host "  Файл .feedback-config.json не найден." -ForegroundColor Yellow
        Write-Host "  Нужен PAT (Personal Access Token) от Daniil'а для claude-base-feedback репо." -ForegroundColor Yellow
        Write-Host ""
        $createNow = Read-Host "  Создать сейчас интерактивно? (y/N)"
        if ($createNow -match '^[yYдД]') {
            Write-Host ""
            Write-Host "  PAT обычно начинается с 'github_pat_' или 'ghp_'. Вставь его сюда (вид скрыт):" -ForegroundColor Cyan
            $secureToken = Read-Host "  Token" -AsSecureString
            $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
            $token = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

            if ($token -and $token.Length -gt 20) {
                # Шифруем через DPAPI CurrentUser (как Set-FeedbackToken.ps1) — plaintext в файл НЕ пишем
                $encrypted = ConvertFrom-SecureString -SecureString $secureToken
                $cfg = @{
                    github_repo     = "K7-LS/claude-base-feedback"
                    token_encrypted = $encrypted
                } | ConvertTo-Json
                [System.IO.File]::WriteAllText($configFile, $cfg, [System.Text.UTF8Encoding]::new($false))
                Write-Host "  [OK] $configFile создан (token зашифрован через DPAPI)" -ForegroundColor Green
                Record "5. Feedback config" "PASS" "created interactively (DPAPI)"
            } else {
                Write-Host "  [SKIP] token пустой/слишком короткий — пропускаем" -ForegroundColor Yellow
                Record "5. Feedback config" "SKIP" "no token entered"
            }
        } else {
            Write-Host "  [SKIP] feedback push отключён до создания .feedback-config.json" -ForegroundColor DarkGray
            Write-Host "         Получи PAT от Daniil'а по secure channel, потом перезапусти Updater." -ForegroundColor DarkGray
            Record "5. Feedback config" "SKIP" "user declined"
        }
    }

    # ===================================================================
    # Step 6: Smoke-test feedback push (только если config есть)
    # ===================================================================
    if (Test-Path $configFile) {
        Section "6. Smoke-test feedback push"
        $pendingDir = Join-Path $ClaudeDir 'feedback-pending'
        New-Item -ItemType Directory -Path $pendingDir -Force | Out-Null
        $smokeFile = Join-Path $pendingDir 'updater-smoke-test.md'

        $smokeContent = @"
## Тип
test

## Описание
Smoke-test feedback pipeline от Updater 2.0 на $env:COMPUTERNAME ($env:USERNAME).
Запущен автоматически из Update-ClaudeBase.ps1.

## Контекст
Проверка end-to-end: feedback-pending → staging → GitHub API push.
Этот файл можно удалить из feedback репо после ревью.

Timestamp: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')
"@
        Set-Content -Path $smokeFile -Value $smokeContent -Encoding UTF8

        # Snapshot лога ДО запуска collector — чтобы потом фильтровать только новые строки
        # (без этого попадают исторические FAIL из прошлых запусков и smoke-test ложно FAIL'ит)
        $logFile = Join-Path $ClaudeDir 'auto-sync.log'
        $linesBefore = if (Test-Path $logFile) {
            @(Get-Content $logFile -Encoding UTF8 -ErrorAction SilentlyContinue).Count
        } else { 0 }

        $collector = Join-Path $ClaudeDir 'scripts\feedback-collector.ps1'
        & powershell -NoProfile -ExecutionPolicy Bypass -File $collector 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

        # Читаем только строки, добавленные ТЕКУЩИМ запуском collector
        $newLines = @()
        if (Test-Path $logFile) {
            $allLines = @(Get-Content $logFile -Encoding UTF8 -ErrorAction SilentlyContinue)
            if ($allLines.Count -gt $linesBefore) {
                $newLines = $allLines[$linesBefore..($allLines.Count - 1)]
            }
        }
        $hasPushed = $newLines | Where-Object { $_ -match 'remote push complete: \d+/\d+' }
        $hasFailed = $newLines | Where-Object { $_ -match 'feedback-collector.*FAILED' }

        if ($hasPushed -and -not $hasFailed) {
            Write-Host "  [OK] Push в GitHub API сработал" -ForegroundColor Green
            $hostname = $env:COMPUTERNAME
            $userPrefix = ($env:USERNAME).ToLower()
            Write-Host "       Branch: feedback/$hostname-$userPrefix" -ForegroundColor DarkGray
            Write-Host "       URL: https://github.com/K7-LS/claude-base-feedback/branches" -ForegroundColor DarkGray
            Record "6. Smoke-test push" "PASS"
        } else {
            Write-Host "  [FAIL] Push в GitHub API не подтверждён" -ForegroundColor Red
            Write-Host "       Новые строки лога (от текущего запуска collector):" -ForegroundColor DarkGray
            if ($newLines.Count -eq 0) {
                Write-Host "       (collector не дописал ничего в лог — возможно failed на старте)" -ForegroundColor DarkGray
            } else {
                $newLines | ForEach-Object { Write-Host "       $_" -ForegroundColor DarkGray }
            }
            $reason = if ($hasFailed) { "collector reported FAILED" } else { "no 'remote push complete' in new log lines" }
            Record "6. Smoke-test push" "FAIL" $reason
        }
    }
}

# ===================================================================
# Final summary
# ===================================================================
Write-Host ""
Write-Host "######################################################" -ForegroundColor Green
Write-Host "###  Summary                                       ###" -ForegroundColor Green
Write-Host "######################################################" -ForegroundColor Green
Write-Host ""

$totalPass = @($script:results | Where-Object { $_.Status -eq 'PASS' }).Count
$totalFail = @($script:results | Where-Object { $_.Status -eq 'FAIL' }).Count
$totalWarn = @($script:results | Where-Object { $_.Status -eq 'WARN' }).Count
$totalSkip = @($script:results | Where-Object { $_.Status -eq 'SKIP' }).Count

foreach ($r in $script:results) {
    $color = switch ($r.Status) {
        'PASS' { 'Green' }
        'FAIL' { 'Red' }
        'WARN' { 'Yellow' }
        'SKIP' { 'DarkGray' }
        default { 'White' }
    }
    $line = "  [$($r.Status)] $($r.Step)"
    if ($r.Detail) { $line += " — $($r.Detail)" }
    Write-Host $line -ForegroundColor $color
}

Write-Host ""
Write-Host "  Total: PASS=$totalPass  FAIL=$totalFail  WARN=$totalWarn  SKIP=$totalSkip" -ForegroundColor Cyan

if ($totalFail -eq 0) {
    Write-Host ""
    Write-Host "  ✅ Готово. claude-base актуальна на $env:COMPUTERNAME." -ForegroundColor Green
    Write-Host ""
    if (-not $isDeveloper) {
        Write-Host "  Что дальше:" -ForegroundColor Cyan
        Write-Host "    - Работаешь в Claude Code как обычно." -ForegroundColor White
        Write-Host "    - При SessionEnd auto-push hook соберёт feedback и отправит в твою ветку." -ForegroundColor White
        Write-Host "    - Daniil заберёт feedback через pull-feedback.ps1 на DANIILPC." -ForegroundColor White
    }
    exit 0
} else {
    Write-Host ""
    Write-Host "  ❌ Есть FAIL. Пришли Daniil'у:" -ForegroundColor Red
    Write-Host "    1. Скрин этого окна (полностью)" -ForegroundColor Red
    Write-Host "    2. Вывод: Get-Content `$HOME\.claude\auto-sync.log -Tail 20" -ForegroundColor Red
    exit 1
}
