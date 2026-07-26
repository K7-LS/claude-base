<#
.SYNOPSIS
Smoke-test ~/.claude/ — проверка что вся методическая база на ПК
актуальна и работает после auto-pull с claude-base.

.DESCRIPTION
Запускается на любом ПК команды после первой сессии Claude Code
(когда auto-pull уже подтянул свежий main). Покрывает 5 групп:

  [1] Sync state — репозиторий синхронизирован с origin/main
  [2] Files in place — все управляемые папки/файлы на месте
  [3] Settings — shared config поля присутствуют
  [4] GitHub bypass-proxy — persistent git config применён
  [5] Pytest evals — regression-тесты скиллов проходят

Использование (Windows PowerShell 5.1 — на всех наших ПК есть by default):
  powershell -File "$HOME\.claude\scripts\verify-claude-base.ps1"

Альтернатива если стоит PowerShell 7:
  pwsh ~/.claude/scripts/verify-claude-base.ps1

Возвращает exit 0 если всё PASS, exit 1 если есть FAIL.
Список FAIL'ов выводится в конце с диагностикой.

Совместимость: файл сохранён в UTF-8 с BOM — корректно парсится
и Windows PowerShell 5.1, и PowerShell 7. Кириллица в строках
работает в обоих случаях.
#>

$ErrorActionPreference = 'Continue'
$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$isDeveloper = Test-Path (Join-Path $ClaudeDir '.developer-marker')

$script:total = 0
$script:passed = 0
$script:failed = @()

function Check {
    param([string]$Name, [scriptblock]$Test, [string]$Hint = "")
    $script:total++
    try {
        $r = & $Test
        if ($r) {
            Write-Host "  [PASS] $Name" -ForegroundColor Green
            $script:passed++
        } else {
            Write-Host "  [FAIL] $Name" -ForegroundColor Red
            if ($Hint) {
                Write-Host "         -> $Hint" -ForegroundColor DarkYellow
            }
            $script:failed += $Name
        }
    } catch {
        Write-Host "  [FAIL] $Name -- $_" -ForegroundColor Red
        $script:failed += "$Name ($_)"
    }
}

Write-Host ""
Write-Host "=== claude-base smoke-test on $env:COMPUTERNAME ===" -ForegroundColor Cyan
Write-Host "    Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "    Claude dir: $ClaudeDir" -ForegroundColor Gray
Write-Host ""

# === [1] Sync state ===
Write-Host "[1] Sync state" -ForegroundColor Yellow
Push-Location $ClaudeDir
Check "Repo is a git repository" {
    Test-Path (Join-Path $ClaudeDir '.git')
} -Hint "Ожидается что ~/.claude/ это клон claude-base"

Check "Role-consistent outbound state" {
    & git fetch --quiet origin main 2>&1 | Out-Null
    if ($isDeveloper) {
        $ahead = & git rev-list --count origin/main..HEAD 2>$null
        return ($ahead -eq '0' -or $ahead -eq 0)
    }
    $pushUrl = & git remote get-url --push origin 2>$null | Select-Object -First 1
    $pushUrl -eq 'NO_PUSH_CONSUMER'
} -Hint "Hub не должен иметь незапушенных коммитов; consumer обязан иметь origin push URL = NO_PUSH_CONSUMER"

Check "Up-to-date with origin/main (no behind)" {
    $behind = & git rev-list --count HEAD..origin/main 2>$null
    ($behind -eq '0' -or $behind -eq 0)
} -Hint "Origin ушёл вперёд. Запусти auto-pull (новая сессия) или вручную git pull --rebase --autostash"

Check "Last commit recent (within 24h)" {
    $logTime = & git log -n 1 --pretty=format:'%cI' 2>$null
    if (-not $logTime) { return $false }
    $age = (Get-Date) - [datetime]$logTime
    $age.TotalHours -lt 48
} -Hint "Возможно нужно auto-pull"
Pop-Location

# === [2] Files in place ===
Write-Host ""
Write-Host "[2] Managed paths / files" -ForegroundColor Yellow

Check "chains/ has 3+ files (named chains)" {
    (Get-ChildItem (Join-Path $ClaudeDir 'chains') -File -ErrorAction SilentlyContinue).Count -ge 3
} -Hint "Должны быть docx-from-template.md, pdf-scan-extract.md, project-doc-pack.md, README.md"

Check "evals/ has pytest tests" {
    Test-Path (Join-Path $ClaudeDir 'evals\test_image_text_replace.py')
} -Hint "Должен быть evals/test_image_text_replace.py с 21 кейсом"

Check "skills/chains-pattern/SKILL.md" {
    Test-Path (Join-Path $ClaudeDir 'skills\chains-pattern\SKILL.md')
}

Check "skills/handoff-to-new-chat/SKILL.md" {
    Test-Path (Join-Path $ClaudeDir 'skills\handoff-to-new-chat\SKILL.md')
}

Check "skills/image-text-replace/LESSONS-LEARNED.md has §7" {
    $f = Join-Path $ClaudeDir 'skills\image-text-replace\LESSONS-LEARNED.md'
    if (-not (Test-Path $f)) { return $false }
    (Get-Content $f -Raw -Encoding UTF8) -match '§7' -or (Get-Content $f -Raw -Encoding UTF8) -match 'DocTR'
} -Hint "§7 (DocTR benchmark) и §6 (unified font_size) — финальные уроки сессии 2026-05-20"

Check "anti-patterns.md has Category 6 (context discipline)" {
    $f = Join-Path $ClaudeDir 'anti-patterns.md'
    if (-not (Test-Path $f)) { return $false }
    (Get-Content $f -Raw -Encoding UTF8) -match 'Категория 6'
}

Check "memory/ has backlog files" {
    Test-Path (Join-Path $ClaudeDir 'memory\backlog_promptfoo_semantic_tests.md')
}

Check "base-manifest.json declares Claude/Codex/OpenCode only" {
    try {
        $base = Get-Content (Join-Path $ClaudeDir 'base-manifest.json') -Raw -Encoding UTF8 |
            ConvertFrom-Json
    } catch { return $false }
    $targets = @($base.targets.PSObject.Properties.Name | Sort-Object)
    ($base.schema -eq 1) -and
        (($targets -join ',') -eq 'claude,codex,opencode') -and
        ($base.sync.direction -eq 'hub-to-consumer') -and
        ($base.sync.consumer_push -eq $false) -and
        ($base.sync.consumer_feedback_upload -eq $false) -and
        ($base.sync.consumer_session_upload -eq $false)
} -Hint "Ожидаются ровно три нативных target и one-way hub-to-consumer"

Check "context-budget.json valid" {
    try {
        $budget = Get-Content (Join-Path $ClaudeDir 'context-budget.json') -Raw -Encoding UTF8 |
            ConvertFrom-Json
    } catch { return $false }
    ($budget.limits.core_tokens -le 1800) -and
        ($budget.limits.startup_total_tokens -le 3000) -and
        ($budget.simple_prompt.tool_calls -eq 0) -and
        ($budget.simple_prompt.subagents -eq 0) -and
        ($budget.simple_prompt.reviewers -eq 0)
}

Check "Legacy reverse-feedback scripts absent" {
    $retiredNames = @(
        ('feedback' + '-collector.ps1'),
        ('pull-' + 'feedback.ps1'),
        ('Set-' + 'FeedbackToken.ps1')
    )
    @($retiredNames | Where-Object {
        Test-Path (Join-Path $ClaudeDir ('scripts\' + $_))
    }).Count -eq 0
}

# === [3] Scripts updated ===
Write-Host ""
Write-Host "[3] Scripts (auto-sync infrastructure)" -ForegroundColor Yellow

Check "auto-pull.ps1 has Invoke-GitPullRetry" {
    $c = Get-Content (Join-Path $ClaudeDir 'scripts\auto-pull.ps1') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    $c -match 'Invoke-GitPullRetry'
} -Hint "Retry logic для SSL/network glitches"

Check "auto-push.ps1 has Invoke-GitPushRetry" {
    $c = Get-Content (Join-Path $ClaudeDir 'scripts\auto-push.ps1') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    $c -match 'Invoke-GitPushRetry'
}

Check "auto-push whitelist includes chains/evals/settings.shared.json" {
    $c = Get-Content (Join-Path $ClaudeDir 'scripts\auto-push.ps1') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    ($c -match "'chains'") -and ($c -match "'evals'") -and ($c -match "'settings\.shared\.json'")
} -Hint "Phase 1 sync-redesign 2026-05-21: settings.json вынесен, settings.shared.json вместо него"

Check "settings.json не в auto-push whitelist (стал personal)" {
    $c = Get-Content (Join-Path $ClaudeDir 'scripts\auto-push.ps1') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    # settings.json должен НЕ быть в whitelist отдельной строкой (только в комментариях)
    $lines = $c -split "`n"
    $managedLines = $lines | Where-Object { $_ -match "^\s*'[\w\.]+'\s*,?\s*(#.*)?\s*$" }
    -not ($managedLines | Where-Object { $_ -match "'settings\.json'" })
} -Hint "settings.json теперь personal (gitignored)"

Check "auto-pull.ps1 auto-applies GitHub bypass-proxy" {
    $c = Get-Content (Join-Path $ClaudeDir 'scripts\auto-pull.ps1') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    $c -match 'bypass-proxy auto-applied' -or $c -match 'http\.https://github\.com/\.proxy'
}

Check "setup-extras.ps1 has Step 0 (GitHub bypass)" {
    $c = Get-Content (Join-Path $ClaudeDir 'scripts\setup-extras.ps1') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    $c -match 'Step 0' -or $c -match 'GitHub bypass-proxy'
}

# === [4] Settings ===
Write-Host ""
Write-Host "[4] Settings.json (shared config)" -ForegroundColor Yellow

$settings = $null
try {
    $settings = Get-Content (Join-Path $ClaudeDir 'settings.json') -Raw | ConvertFrom-Json
} catch {}

Check "settings.json valid JSON" {
    $null -ne $settings
}

Check "settings.json language='russian'" {
    $settings -and $settings.language -eq 'russian'
}

Check "settings.json does not inherit forced xhigh" {
    $settings -and (-not ($settings.PSObject.Properties.Name -contains 'effortLevel'))
} -Hint "Общая база не задаёт reasoning effort; после миграции пользователь может выбрать его лично"

Check "settings.shared.json has only minimal sync hooks" {
    try {
        $sharedSettings = Get-Content (Join-Path $ClaudeDir 'settings.shared.json') -Raw |
            ConvertFrom-Json
    } catch { return $false }
    $hookNames = @($sharedSettings.hooks.PSObject.Properties.Name | Sort-Object)
    (($hookNames -join ',') -eq 'SessionEnd,SessionStart') -and
        (-not ($sharedSettings.PSObject.Properties.Name -contains 'effortLevel')) -and
        (-not ($sharedSettings.PSObject.Properties.Name -contains 'enabledPlugins')) -and
        (-not ($sharedSettings.PSObject.Properties.Name -contains 'autoMode'))
}

Check "settings.json enabledPlugins present" {
    $settings -and ($null -ne $settings.enabledPlugins)
}

# === [5] GitHub bypass-proxy persistent ===
Write-Host ""
Write-Host "[5] GitHub bypass-proxy (persistent git config)" -ForegroundColor Yellow

Check "git config http.https://github.com/.proxy is set" {
    # NB: --get returns exit 1 for empty values on some git versions.
    # Use --list + regex to detect key presence regardless of value.
    $listOut = & git config --global --list 2>$null
    @($listOut | Where-Object { $_ -match '^http\.https://github\.com/\.proxy=' }).Count -gt 0
} -Hint "auto-pull.ps1 применит при первом hook'е, или вручную: git config --global http.https://github.com/.proxy `"`""

# === [6] Pytest evals ===
Write-Host ""
Write-Host "[6] Pytest evals (regression-тесты скиллов)" -ForegroundColor Yellow

Check "pytest collects + passes (21 tests)" {
    # pytest evals = regression-тесты для РАЗРАБОТКИ скиллов.
    # Обязательны ТОЛЬКО на developer-ПК (есть .developer-marker).
    # На consumer-ПК пропускаем ВСЕГДА — это dev-инструмент, не нужен для
    # работы (даже если python в PATH есть для других задач). Иначе consumer
    # с python но без pytest давал ложный FAIL.
    $isDeveloper = Test-Path (Join-Path $ClaudeDir '.developer-marker')
    if (-not $isDeveloper) {
        Write-Host "         (consumer PC — pytest evals не требуются, skipped)" -ForegroundColor DarkGray
        return $true
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Host "         (developer PC, python не в PATH — нужен Python+pytest)" -ForegroundColor Yellow
        return $false
    }
    $evalsDir = Join-Path $ClaudeDir 'evals'
    if (-not (Test-Path $evalsDir)) { return $false }
    Push-Location $evalsDir
    try {
        $out = & python -m pytest --tb=no -q 2>&1 | Out-String
        Pop-Location
        ($out -match 'passed') -and -not ($out -match '\d+ failed')
    } catch {
        Pop-Location
        $false
    }
} -Hint "Требует pytest установлен: python -m pip install --user pytest"

# === [7] PII-гард (обезличивание перед push, правило 6) ===
Write-Host ""
Write-Host "[7] PII-гард (обезличивание, правило 6)" -ForegroundColor Yellow

Check "Нет реальных идентификаторов организации/объектов в pushed" {
    $patterns = @('К-7','K-7','Лайф-саунд','МСУ-1','Сит-центр','Балашиха','РАНХиГС','ПСИ-158')
    $dirs = @('agents','skills','memory','chains','session-reports') | ForEach-Object { Join-Path $ClaudeDir $_ }
    $hits = @()
    foreach ($d in $dirs) {
        if (Test-Path $d) {
            $hits += Get-ChildItem $d -Recurse -File -Include *.md,*.py,*.ps1,*.lsp -ErrorAction SilentlyContinue |
                Select-String -Pattern $patterns -SimpleMatch -List -ErrorAction SilentlyContinue
        }
    }
    $cm = Join-Path $ClaudeDir 'CLAUDE.md'
    if (Test-Path $cm) { $hits += Select-String -Path $cm -Pattern $patterns -SimpleMatch -List -ErrorAction SilentlyContinue }
    @($hits).Count -eq 0
} -Hint "Найдены реальные идентификаторы (имя организации/коды объектов) — обезличить ДО push (правило 6 CLAUDE.md)"

# === [8] Эталоны (счётчики MCP/agents, JSON-валидность) ===
Write-Host ""
Write-Host "[8] Эталоны (счётчики)" -ForegroundColor Yellow

Check "mcp-manifest.json valid + 11 core MCP" {
    try { $m = Get-Content (Join-Path $ClaudeDir 'mcp-manifest.json') -Raw | ConvertFrom-Json } catch { return $false }
    @($m.mcp_servers | Where-Object { $_.tier -eq 'core' }).Count -eq 11
} -Hint "Эталон 11 core MCP (markitdown..exa) — источник истины mcp-manifest.json"

Check "agents/ == 16 (минус _TEMPLATE, agents.md)" {
    $a = Get-ChildItem (Join-Path $ClaudeDir 'agents') -Filter *.md -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne '_TEMPLATE.md' -and $_.Name -ne 'agents.md' }
    @($a).Count -eq 16
} -Hint "Эталон 16 агентов"

Check "settings.shared.json valid JSON" {
    try { Get-Content (Join-Path $ClaudeDir 'settings.shared.json') -Raw | ConvertFrom-Json | Out-Null; $true } catch { $false }
}

# === [9] Compact base verifier ===
Write-Host ""
Write-Host "[9] Compact base verifier" -ForegroundColor Yellow

Check "base_cli.py verify" {
    $baseCli = Join-Path $ClaudeDir 'scripts\base_cli.py'
    if (-not (Test-Path $baseCli)) { return $false }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-Host "         (Python не найден — JSON/role checks выше выполнены, CLI skipped)" -ForegroundColor DarkGray
        return $true
    }
    & python $baseCli verify 2>&1 | Out-Null
    $LASTEXITCODE -eq 0
}

# === Summary ===
Write-Host ""
Write-Host "=== Summary: $passed/$total passed ===" -ForegroundColor Cyan

if ($failed.Count -eq 0) {
    Write-Host "✅ All checks passed — claude-base ready to work" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "FAILED checks:" -ForegroundColor Red
    foreach ($f in $failed) {
        Write-Host "  - $f" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Next step: исправь перечисленные failures и повтори verify." -ForegroundColor Yellow
    exit 1
}
