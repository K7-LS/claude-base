<#
.SYNOPSIS
SessionEnd hook: commit and push managed paths in ~/.claude/ to claude-base.

.DESCRIPTION
Triggered by Claude Code on session end (settings.json hooks).
Checks git status of WHITELIST paths. If there are changes -- commits and
pushes to origin/main. Logs to ~/.claude/auto-sync.log.

Whitelist (managed paths -- only these are auto-committed):
    agents/, skills/, commands/, memory/, session-reports/, harvested/,
    CLAUDE.md, README.md

Anything outside the whitelist is NEVER auto-committed -- protects against
accidental push of credentials, history, plugins, projects, _sandbox, etc.
Those are also gitignored, but defense in depth.

Always exits 0 to avoid blocking session end.

Conflict handling: pulls before pushing. If pull conflicts, aborts and skips
push. User resolves on next manual interaction.
#>

$ErrorActionPreference = 'SilentlyContinue'

$claudeDir = Join-Path $env:USERPROFILE '.claude'
$logFile   = Join-Path $claudeDir 'auto-sync.log'

# Whitelist of managed paths. Files OUTSIDE these are NEVER auto-committed.
# IMPORTANT: 'sessions' is intentionally NOT in this list -- Claude Code
# itself uses ~/.claude/sessions/ for transient JSON session state. Our
# per-session reports go to session-reports/ (different name to avoid
# collision).
$Managed = @(
    'agents',
    'skills',
    'commands',
    'memory',
    'session-reports',
    'harvested',
    'formatting-templates',
    'CLAUDE.md',
    'README.md',
    'CHANGELOG.md',
    # === Added 2026-05-20 (gap-fix sync) ===
    # Эти пути ранее не были в whitelist — изменения требовали ручного
    # git commit + push. Теперь auto-push их подхватывает автоматически.
    'chains',
    'evals',
    'anti-patterns.md',
    'scripts',
    'mcp-manifest.json',
    '.gitignore',
    'settings.shared.json',
    # === Added 2026-05-26 ===
    # docs/ — дизайн-спецификации (output из superpowers:brainstorming skill).
    # Крупная задача → spec в docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
    # → план → имплементация. Spec'и в git, видны всей команде.
    'docs'
    # NOTE: settings.json больше НЕ в whitelist (2026-05-21 Phase 1).
    # Причина: Claude Code UI постоянно пишет в settings.json (theme,
    # viewMode и т.п.) → race conditions между ПК. Теперь:
    #   ~/.claude/settings.json         — personal, gitignored
    #   ~/.claude/settings.shared.json  — shared, в репо
    #   scripts/merge-shared-settings.ps1 — вливает shared в personal
    # См. design.md в session-reports/2026-05-21_sync-redesign/.
)

function Write-SyncLog { param($msg)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] auto-push: $msg" | Add-Content -Path $logFile
}

# === Зонд hook-input (Фаза 0, 2026-07-02): что реально приходит на stdin ===
# Claude Code передаёт хуку JSON через stdin. Читаем только при redirected stdin
# (ручной запуск без пайпа не виснет). Сырой payload — в hook-probe.jsonl.
$hookInput = $null
try {
    if ([Console]::IsInputRedirected) {
        # UTF-8 stdin ОБЯЗАТЕЛЕН (тот же класс, что чинил Блок 2 в log-tool-usage.ps1):
        # без этого PS 5.1 читает OEM, кириллица в transcript_path ("Даниил") превращается
        # в мусор, Test-Path не находит транскрипт — и гейт эфемерных сессий резал
        # НАСТОЯЩИЕ SessionEnd (инцидент 02–07.07: 5 коммитов копились локально).
        try {
            [Console]::InputEncoding  = New-Object System.Text.UTF8Encoding($false)
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        } catch { }
        $rawInput = [Console]::In.ReadToEnd()
        if ($rawInput) { $rawInput = $rawInput.Trim([char]0xFEFF) }
        if ($rawInput -and $rawInput.Trim()) {
            $probeFile = Join-Path $claudeDir '.local-state\hook-probe.jsonl'
            Add-Content -Path $probeFile -Value ("[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')][auto-push] " + $rawInput.Trim())
            $hookInput = $rawInput | ConvertFrom-Json
        }
    }
} catch {}

# Retry wrapper для git push. Retryable: SSL handshake, schannel/TLS,
# transient network, DNS, connection reset, timeout. 3 попытки с 5-сек паузой.
# НЕ retryable: 403 denied, non-fast-forward (нужен pull + rebase).
function Invoke-GitPushRetry {
    param([int]$MaxAttempts = 3, [int]$DelaySec = 5)
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        $out = & git -c http.proxy="" -c https.proxy="" push origin main 2>&1
        $exit = $LASTEXITCODE
        if ($exit -eq 0) {
            return @{ Success = $true; Output = $out; Attempts = $i }
        }
        $text = ($out | Out-String)
        $isRetryable = (
            $text -match 'schannel' -or
            $text -match 'SSL/TLS' -or
            $text -match 'handshake' -or
            $text -match 'Connection reset' -or
            $text -match 'Could not resolve' -or
            $text -match 'Failed to connect' -or
            $text -match 'transient' -or
            $text -match 'Operation timed out'
        )
        if (-not $isRetryable -or $i -eq $MaxAttempts) {
            return @{ Success = $false; Output = $out; Attempts = $i }
        }
        Write-SyncLog "push attempt $i/$MaxAttempts failed (retryable: SSL/network), retry in ${DelaySec}s..."
        Start-Sleep -Seconds $DelaySec
    }
}

# Skip if ~/.claude/ is not a git repo
if (-not (Test-Path (Join-Path $claudeDir '.git'))) {
    exit 0
}

Push-Location $claudeDir
try {
    # Pre-flight: проверить не была ли прервана предыдущая операция
    $lastLines = Get-Content $logFile -Tail 8 -ErrorAction SilentlyContinue
    if ($lastLines) {
        $lastEntry = ($lastLines | Where-Object { $_ -match 'auto-(pull|push):' } | Select-Object -Last 1)
        if ($lastEntry -match 'auto-(pull|push): start' -and
            $lastEntry -notmatch 'DONE|ok|FAILED|pushed|no managed') {
            Write-SyncLog "WARN: previous hook was interrupted (last: '$lastEntry'). Возможно timeout или kill."
        }
    }

    # === Role detection (Phase 2 sync-redesign 2026-05-21) ===
    # DANIILPC (developer) имеет .developer-marker — push'ит в main как обычно.
    # Сотрудники без marker'а — consumer mode: запускают feedback-collector
    # вместо push в main. Это разделяет hub-and-spoke: Daniil = writer, остальные = read+feedback.
    $isDeveloper = Test-Path (Join-Path $claudeDir '.developer-marker')
    if (-not $isDeveloper) {
        Write-SyncLog "consumer mode (no .developer-marker) — running feedback-collector"
        $feedbackScript = Join-Path $claudeDir 'scripts\feedback-collector.ps1'
        if (Test-Path $feedbackScript) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $feedbackScript 2>&1 | Out-Null
            Write-SyncLog "feedback-collector finished"
        } else {
            Write-SyncLog "feedback-collector.ps1 not found — skip"
        }
        Write-SyncLog "DONE (consumer)"
        # Pop-Location здесь НЕ нужен: exit внутри try гарантированно вызывает
        # finally (Pop-Location там) — явный вызов давал двойной Pop (MINOR аудита)
        exit 0
    }

    Write-SyncLog "start"

    # === Гейт эфемерных сессий (2026-07-02, «правильное» по разбору Блока 3;
    #     усилен после NOT PASSED аудита — двухфакторный критерий) ===
    # ФАКТ (зонд hook-probe.jsonl): one-shot/headless-инвокации (claude -p,
    # служебные хелперы) дают полный цикл SessionStart→SessionEnd за секунды,
    # и их SessionEnd свипал в commit+push ЧУЖУЮ незавершённую работу (кейс
    # 12:18–12:25 02.07). Субагенты SessionEnd НЕ стреляют (живой тест).
    # Критерий эфемерности ДВУХФАКТОРНЫЙ: мало строк И короткая длительность
    # (по timestamp первой/последней записи транскрипта). Однофакторный «строк
    # < 10» ловил настоящие короткие сессии (аудит нашёл реальный 9-строчный
    # транскрипт) — но у него длительность 0.118 с = стаб; настоящая сессия
    # живёт минуты. По reason НЕ гейтим («other» может приходить и у настоящих
    # закрытий → риск отключить sync). Гейт стоит ПОСЛЕ consumer-ветки
    # НАМЕРЕННО: feedback-collector на consumer-ПК работает как раньше
    # (идемпотентен, глушить его нет причины).
    # Fail-open: нет stdin/поля/строк/распарсенной длительности → пуш идёт.
    $EphemeralMaxLines = 10
    $EphemeralMaxSeconds = 60
    if ($hookInput -and $hookInput.transcript_path) {
        $tp = [string]$hookInput.transcript_path
        $isSubagent = ($tp -match '[\\/]subagents[\\/]')
        $lineCount = $null; $durationSec = $null
        if (Test-Path $tp) {
            try {
                $tLines = [IO.File]::ReadAllLines($tp)
                $lineCount = $tLines.Count
                $reTs = '"timestamp"\s*:\s*"([^"]+)"'
                $tsFirst = $null; $tsLast = $null
                foreach ($l in $tLines) {
                    $m = [regex]::Match($l, $reTs)
                    if ($m.Success) { $tsFirst = $m.Groups[1].Value; break }
                }
                for ($j = $tLines.Count - 1; $j -ge 0; $j--) {
                    $m = [regex]::Match($tLines[$j], $reTs)
                    if ($m.Success) { $tsLast = $m.Groups[1].Value; break }
                }
                if ($tsFirst -and $tsLast) {
                    $durationSec = ([datetime]::Parse($tsLast) - [datetime]::Parse($tsFirst)).TotalSeconds
                }
            } catch { $lineCount = $null; $durationSec = $null }
        }
        $isTiny = ($null -ne $lineCount) -and ($lineCount -lt $EphemeralMaxLines) -and
                  ($null -ne $durationSec) -and ($durationSec -lt $EphemeralMaxSeconds)
        # 2026-07-07: отсутствующий транскрипт = FAIL-OPEN (пуш идёт), как и задекларировано
        # выше. Старое "-not (Test-Path $tp) => ephemeral" при сломанной кодировке stdin
        # резало ВСЕ настоящие концы сессий. Субагентов и так ловит матч по пути.
        if ((-not $isSubagent) -and (-not (Test-Path $tp))) {
            Write-SyncLog "transcript not found ($tp) -- fail-open, treating as real SessionEnd"
        }
        $isEphemeral = $isSubagent -or $isTiny
        if ($isEphemeral) {
            Write-SyncLog "skip: ephemeral/subagent SessionEnd (session=$($hookInput.session_id), reason=$($hookInput.reason), lines=$lineCount, duration_sec=$durationSec) -- пуш пропущен, изменения уедут на настоящем конце сессии"
            exit 0
        }
        # телеметрия для аудита непропущенных (дёшево, 1 строка на настоящий конец сессии)
        Write-SyncLog "real SessionEnd (session=$($hookInput.session_id), reason=$($hookInput.reason), lines=$lineCount, duration_sec=$durationSec)"
    }

    # Defense-in-depth: disable interactive credential prompt and clear
    # proxy env-vars at the top of the hook -- applies to BOTH fetch
    # (in the ahead-origin check below) and push (later). See traps
    # 14 (hook hangs on prompt) and 15 (proxy env breaks git push)
    # in memory/2026-05-09_hooks-debugging.md.
    $env:GIT_TERMINAL_PROMPT = '0'
    Remove-Item Env:HTTP_PROXY  -ErrorAction SilentlyContinue
    Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:http_proxy  -ErrorAction SilentlyContinue
    Remove-Item Env:https_proxy -ErrorAction SilentlyContinue
    Remove-Item Env:ALL_PROXY   -ErrorAction SilentlyContinue
    Remove-Item Env:all_proxy   -ErrorAction SilentlyContinue

    # Find managed paths with changes in working tree
    $changedPaths = @()
    foreach ($path in $Managed) {
        if (-not (Test-Path $path)) { continue }
        $status = & git status --porcelain -- $path 2>$null
        if ($status) { $changedPaths += $path }
    }

    if ($changedPaths.Count -eq 0) {
        # No working tree changes -- but maybe local commits are ahead origin.
        # Scenario: user (or Claude in chat) did `git commit` manually but
        # `git push` failed (network, missing PAT, etc). Working tree is clean,
        # the previous hook logic exited without push, and these commits
        # would never reach origin on their own.
        #
        # Quick fetch to refresh origin/main ref (safe in hook context --
        # unlike `git pull --rebase` which hangs, fetch is read-only).
        & git -c http.proxy="" -c https.proxy="" fetch --quiet origin main 2>&1 | Out-Null
        $aheadOut = & git rev-list --count origin/main..HEAD 2>$null
        $aheadCount = if ($aheadOut) { [int]$aheadOut } else { 0 }

        if ($aheadCount -eq 0) {
            Write-SyncLog "no managed changes, no commits ahead origin"
            exit 0
        }
        Write-SyncLog "no working tree changes, but $aheadCount commit(s) ahead -- proceeding to push"
    } else {
        Write-SyncLog "managed changes in: $($changedPaths -join ', ')"

        # Индекс принадлежит текущей ручной операции. Обычный `git commit`
        # захватил бы эти изменения вместе с whitelist hook-а, поэтому до
        # следующего настоящего конца сессии только сохраняем их нетронутыми.
        $preExistingStaged = @(& git diff --cached --name-only 2>$null)
        if ($preExistingStaged.Count -gt 0) {
            Write-SyncLog "skip: pre-existing staged changes ($($preExistingStaged -join ', ')) -- auto-commit deferred"
            exit 0
        }

        # Stage changes
        foreach ($path in $changedPaths) {
            & git add -- $path 2>&1 | Out-Null
        }

        # === Обезличивание (2026-07-02, смягчённое правило владельца) ===
        # Строгий ярус (ФИО/шифры/реквизиты — regex в stoplist) → файл СНИМАЕТСЯ со
        # staging (не уезжает, лежит локально до ручной чистки) + лог + pending-файл.
        # Warn-ярус (имена объектов — разрешены по делу) → только строка в лог, пуш идёт.
        # Словарь НЕ в git (.local-state гитигнорен — сам словарь содержит маркеры).
        $stopFile = Join-Path $claudeDir '.local-state\anonymize-stoplist.txt'
        if (-not (Test-Path $stopFile)) {
            # Гард без словаря молча выключен — этого больше не допускаем (ревизия 2026-08-26)
            Write-SyncLog "anonymize: stoplist MISSING -- PII-guard OFF; создай .local-state\anonymize-stoplist.txt (strict:/warn: паттерны)"
        }
        if (Test-Path $stopFile) {
            $strictPats = @(); $warnPats = @()
            foreach ($line in (Get-Content $stopFile -Encoding UTF8)) {
                $t = $line.Trim()
                if (-not $t -or $t.StartsWith('#')) { continue }
                if ($t.StartsWith('strict:'))   { $strictPats += $t.Substring(7).Trim() }
                elseif ($t.StartsWith('warn:')) { $warnPats   += $t.Substring(5).Trim() }
            }
            $stagedFiles = & git diff --cached --name-only 2>$null
            $pendingFile = Join-Path $claudeDir '.local-state\anonymize-pending.txt'
            foreach ($f in $stagedFiles) {
                $full = Join-Path $claudeDir $f
                if (-not (Test-Path $full)) { continue }              # удалённые — мимо
                if ($f -notmatch '\.(md|txt|json|yaml|yml|py|ps1|csv)$') { continue }
                $content = ''
                try { $content = [IO.File]::ReadAllText($full, [Text.Encoding]::UTF8) } catch { continue }
                $hit = $null
                foreach ($p in $strictPats) { if ($content -match $p) { $hit = $p; break } }
                if ($hit) {
                    & git reset -q -- $f 2>&1 | Out-Null
                    Write-SyncLog "ANONYMIZE-BLOCK: $f (strict-маркер) -- НЕ запушен; вычисти и закоммить вручную"
                    Add-Content -Path $pendingFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm') | $f"
                    continue
                }
                foreach ($p in $warnPats) {
                    if ($content -match [regex]::Escape($p)) {
                        Write-SyncLog "ANONYMIZE-WARN: $f содержит '$p' (разрешено; проверь, что умышленно)"
                        break
                    }
                }
            }
        }

        # Commit (skip if nothing was actually staged after add)
        $hostname = $env:COMPUTERNAME
        $msg = "auto-sync: session $(Get-Date -Format 'yyyy-MM-dd HH:mm') from $hostname"
        $commitOut = & git commit -m $msg 2>&1
        $commitExit = $LASTEXITCODE

        $commitOut | Out-String | Add-Content -Path $logFile

        if ($commitExit -ne 0) {
            Write-SyncLog "commit returned exit=$commitExit (likely nothing to commit)"
            exit 0
        }

        Write-SyncLog "commit ok"
    }

    # Push (shared path: covers both fresh-commit-from-staging and ahead-origin cases)
    # Empirically, `git pull --rebase --autostash` hangs in Claude Code
    # SessionEnd hook context, so we never pre-pull. If push gets rejected
    # (remote moved), local commit stays ahead -- next SessionStart auto-pull
    # rebases, next SessionEnd retries push. Eventually consistent.

    # GIT_TERMINAL_PROMPT=0 and proxy env-cleanup applied at hook start
    # (traps 14, 15) -- still in effect for this push.

    Write-SyncLog "pushing to origin/main..."
    $pushResult = Invoke-GitPushRetry -MaxAttempts 3 -DelaySec 5
    $pushOut = $pushResult.Output
    $pushExit = if ($pushResult.Success) { 0 } else { 1 }
    $pushOut | Out-String | Add-Content -Path $logFile

    if ($pushExit -eq 0) {
        $tag = if ($pushResult.Attempts -gt 1) { "pushed to origin/main (after $($pushResult.Attempts) attempts)" } else { "pushed to origin/main" }
        Write-SyncLog $tag
    } else {
        Write-SyncLog "push FAILED (exit=$pushExit) -- commit stays ahead, will retry next cycle"

        # Smart diagnostic: parse `denied to <user>` to distinguish trap 12a
        # (expired/wrong-scope PAT for repo owner) from 12b (wrong account
        # entirely -- collaborator missing). See memory/2026-05-09_hooks-debugging.md.
        $pushText = ($pushOut | Out-String)
        if ($pushText -match 'denied to (?<user>[\w.-]+)') {
            $deniedUser = $Matches['user']
            # Extract repo owner from origin URL
            $originUrl = & git remote get-url origin 2>$null
            if ($originUrl -match 'github\.com[:/](?<owner>[\w.-]+)/') {
                $repoOwner = $Matches['owner']
                if ($deniedUser -eq $repoOwner) {
                    Write-SyncLog "diagnose: 403 denied to '$deniedUser' (owner) -- likely expired PAT or insufficient scope (trap 12a). Run: cmdkey /delete:LegacyGeneric:target=git:https://github.com  then re-push."
                } else {
                    Write-SyncLog "diagnose: 403 denied to '$deniedUser' (not owner '$repoOwner') -- WRONG ACCOUNT or missing collaborator (trap 12b). Owner must add '$deniedUser' as collaborator in repo Settings."
                }
            }
        } elseif ($pushText -match 'Proxy CONNECT aborted') {
            Write-SyncLog "diagnose: proxy CONNECT aborted -- corp proxy blocking git. Check whether HTTP_PROXY env is needed for git on this machine (often NOT). See trap 6, 15."
        } elseif ($pushText -match 'could not read Username') {
            Write-SyncLog "diagnose: GIT_TERMINAL_PROMPT=0 prevented interactive auth -- means credentials missing. Run `git push origin main` manually once to trigger Credential Manager flow."
        }
    }
} catch {
    Write-SyncLog "exception: $_"
} finally {
    Pop-Location
    Write-SyncLog "DONE"
}

# Always exit 0 -- never block session end
exit 0
