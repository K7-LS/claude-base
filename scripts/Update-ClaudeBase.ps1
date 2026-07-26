<#
.SYNOPSIS
Updater 2.0 — one-command setup + проверка claude-base на любом ПК команды.

.DESCRIPTION
Один скрипт делает всё что раньше было 8 ручных шагов:

  [1] Detect role (developer vs consumer по .developer-marker)
  [2] git pull origin main (с retry + bypass-proxy)
  [3] merge-shared-settings.ps1 (shared → personal settings.json)
  [4] verify-claude-base.ps1 (22 проверки)
  [5] Для consumer отключить push URL (read-only defense in depth)
  [6] Финальный summary с PASS/FAIL по каждому шагу

Запуск:
  - Double-click `Update-ClaudeBase.bat` в проводнике (рекомендуется)
  - Либо: powershell -File "$HOME\.claude\scripts\Update-ClaudeBase.ps1"

Возвращает exit 0 если всё PASS, exit 1 если есть FAIL.
#>

$ErrorActionPreference = 'Continue'
$ClaudeDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

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
    Write-Host "  -> Разрешена публикация после проверок." -ForegroundColor DarkGray
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
# Step 5: Consumer read-only guard
# ===================================================================
if (-not $isDeveloper) {
    Section "5. Consumer read-only guard"
    Push-Location $ClaudeDir
    try {
        & git remote set-url --push origin 'NO_PUSH_CONSUMER' 2>&1 | Out-Null
        $pushUrl = (& git remote get-url --push origin 2>$null | Select-Object -First 1)
        if ($pushUrl -eq 'NO_PUSH_CONSUMER') {
            Write-Host "  [OK] origin push disabled" -ForegroundColor Green
            Record "5. Consumer read-only" "PASS"
        } else {
            Write-Host "  [FAIL] origin push URL remains writable" -ForegroundColor Red
            Record "5. Consumer read-only" "FAIL"
        }
    } finally {
        Pop-Location
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
        Write-Host "    - Обновления приходят через SessionStart или /sync-base." -ForegroundColor White
        Write-Host "    - SessionEnd ничего не отправляет с этого ПК." -ForegroundColor White
    }
    exit 0
} else {
    Write-Host ""
    Write-Host "  ❌ Есть FAIL. Пришли Daniil'у:" -ForegroundColor Red
    Write-Host "    1. Скрин этого окна (полностью)" -ForegroundColor Red
    Write-Host "    2. Вывод: Get-Content `$HOME\.claude\auto-sync.log -Tail 20" -ForegroundColor Red
    exit 1
}
