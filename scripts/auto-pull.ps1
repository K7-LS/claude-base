<#
.SYNOPSIS
SessionStart hook: pull latest LLM-base in its build-repository.

.DESCRIPTION
Triggered by Claude Code on session start (settings.json hooks).
Runs git pull --rebase --autostash silently. Logs to ~/.claude/auto-sync.log.
Always exits 0 to avoid blocking session start.

If there is a rebase conflict (rare; happens when CORE block of CLAUDE.md
was edited locally AND in claude-base) -- aborts the rebase, leaves the
working tree as-is, logs the failure. User resolves manually.
#>

$ErrorActionPreference = 'SilentlyContinue'

$claudeDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$logFile   = Join-Path $claudeDir 'auto-sync.log'

function Write-SyncLog { param($msg)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] auto-pull: $msg" | Add-Content -Path $logFile
}

# === Зонд hook-input (Фаза 0, 2026-07-02): что реально приходит на stdin ===
# Claude Code передаёт хуку JSON через stdin. Читаем только при redirected stdin
# (ручной запуск без пайпа не виснет). Сырой payload — в hook-probe.jsonl.
$hookInput = $null
try {
    if ([Console]::IsInputRedirected) {
        # UTF-8 stdin — иначе PS 5.1 читает OEM и кириллица в путях payload'а
        # превращается в мусор в hook-probe.jsonl (тот же фикс, что в auto-push).
        try {
            [Console]::InputEncoding  = New-Object System.Text.UTF8Encoding($false)
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        } catch { }
        $rawInput = [Console]::In.ReadToEnd()
        if ($rawInput) { $rawInput = $rawInput.Trim([char]0xFEFF) }
        if ($rawInput -and $rawInput.Trim()) {
            $probeFile = Join-Path $claudeDir '.local-state\hook-probe.jsonl'
            Add-Content -Path $probeFile -Value ("[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')][auto-pull] " + $rawInput.Trim())
            $hookInput = $rawInput | ConvertFrom-Json
        }
    }
} catch {}

# Retry wrapper для git pull. Retryable errors:
# SSL handshake glitches, schannel/TLS, transient network, DNS, connection reset.
# 3 попытки с 5-сек паузой между ними.
function Invoke-GitPullRetry {
    param([int]$MaxAttempts = 3, [int]$DelaySec = 5)
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        $out = & git -c http.proxy="" -c https.proxy="" pull --rebase --autostash 2>&1
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
        Write-SyncLog "pull attempt $i/$MaxAttempts failed (retryable: SSL/network), retry in ${DelaySec}s..."
        Start-Sleep -Seconds $DelaySec
    }
}

# Skip if ~/.claude/ is not a git repo
if (-not (Test-Path (Join-Path $claudeDir '.git'))) {
    exit 0
}

Push-Location $claudeDir
try {
    # Defense in depth: consumer получает origin, но локальный push URL
    # намеренно не является сетевым адресом. Даже ручной `git push` не отправит
    # данные. При явном переводе машины в hub восстанавливаем fetch URL, только
    # если ранее стоял наш sentinel; пользовательский SSH push URL не трогаем.
    $isDeveloper = Test-Path (Join-Path $claudeDir '.developer-marker')
    $fetchUrl = (& git remote get-url origin 2>$null | Select-Object -First 1)
    $pushUrl = (& git remote get-url --push origin 2>$null | Select-Object -First 1)
    if (-not $isDeveloper) {
        if ($pushUrl -ne 'NO_PUSH_CONSUMER') {
            & git remote set-url --push origin 'NO_PUSH_CONSUMER' 2>&1 | Out-Null
            Write-SyncLog "consumer read-only: origin push URL disabled"
        }
    } elseif ($pushUrl -eq 'NO_PUSH_CONSUMER' -and $fetchUrl) {
        & git remote set-url --push origin $fetchUrl 2>&1 | Out-Null
        Write-SyncLog "hub marker detected: origin push URL restored"
    }

    # Pre-flight: проверить не была ли прервана предыдущая операция
    $lastLines = Get-Content $logFile -Tail 8 -ErrorAction SilentlyContinue
    if ($lastLines) {
        $lastEntry = ($lastLines | Where-Object { $_ -match 'auto-(pull|push):' } | Select-Object -Last 1)
        if ($lastEntry -match 'auto-(pull|push): start' -and
            $lastEntry -notmatch 'DONE|ok|FAILED|pushed|no managed') {
            Write-SyncLog "WARN: previous hook was interrupted (last: '$lastEntry'). Возможно timeout или kill."
        }
    }

    Write-SyncLog "start"

    # === Wedge-детект: sync застрял конфликтом слияния? (feedback infra 2026-06-08) ===
    # Если предыдущий autostash-pop оставил конфликт-маркеры, КАЖДЫЙ pull падает на
    # 'unmerged files' и база молча не обновляется (реальный кейс: consumer отстал на
    # 64 коммита незаметно — лог никто не читает). Детектим ДО pull, ГРОМКО предупреждаем
    # в контекст сессии, pull НЕ делаем (не усугубляем). Авто-reset не делаем намеренно —
    # восстановление за пользователем (managed-сброс к origin рискован без подтверждения).
    $wedge = & git status --porcelain 2>$null | Where-Object { $_ -match '^(UU|AA|DD|AU|UA|DU|UD)' }
    if ($wedge) {
        $files = (($wedge | ForEach-Object { ($_ -replace '^..\s+','') }) -join '; ')
        Write-SyncLog "WEDGE detected (unmerged files) — pull пропущен. Files: $files"
        $warn = "⚠ claude-base sync ЗАКЛИНЕН конфликтом слияния (unmerged files) — авто-обновление НЕ работает, база может молча отставать. Файлы: $files. Восстановление: бэкап → 'git checkout HEAD -- <файлы>' + 'git stash drop'; для consumer-ПК managed-файлы можно сбросить 'git reset --hard origin/main'. Затем повторить сессию."
        @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $warn } } |
            ConvertTo-Json -Compress -Depth 4 | Write-Output
        exit 0   # finally сделает Pop-Location + DONE
    }

    # === Zero-touch GitHub bypass-proxy (idempotent) ===
    # Корп-прокси блокирует CONNECT к github.com. Для ручных git/gh операций
    # пользователю нужен persistent global config bypass. Применяем сами при
    # первом auto-pull на каждом ПК. Idempotent — если уже настроено, skip.
    # См. CLAUDE.md раздел "GitHub — обязательный bypass proxy".
    # Проверка через $LASTEXITCODE: git config --get выдаёт exit 1 когда
    # ключ не существует и exit 0 когда существует (даже со значением "").
    # Это однозначно работает и в PS 5.1, и в PS Core 7 — в отличие от
    # проверки stdout через `$null -eq $x`, которая ломается в PS 5.1
    # (там пустой stdout возвращается как "" а не $null).
    & git config --global --get http.https://github.com/.proxy 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & git config --global http.https://github.com/.proxy "" 2>&1 | Out-Null
        & git config --global https.https://github.com/.proxy "" 2>&1 | Out-Null
        Write-SyncLog "GitHub bypass-proxy auto-applied (was unset) — manual git/gh ops к GitHub теперь работают без -c флагов"
    }

    # Sanity check ДО pull — узнать сколько коммитов мы behind
    & git fetch --quiet origin main 2>&1 | Out-Null
    $beforeBehind = & git rev-list --count HEAD..origin/main 2>$null
    if ($beforeBehind -and [int]$beforeBehind -gt 0) {
        Write-SyncLog "behind origin by $beforeBehind commit(s), will rebase"
    }

    $pullResult = Invoke-GitPullRetry -MaxAttempts 3 -DelaySec 5
    $output = $pullResult.Output
    $exit = if ($pullResult.Success) { 0 } else { 1 }

    $output | Out-String | Add-Content -Path $logFile

    if ($exit -ne 0) {
        Write-SyncLog "FAILED after $($pullResult.Attempts) attempt(s), aborting rebase"
        & git rebase --abort 2>&1 | Out-Null
    } else {
        # Sanity check ПОСЛЕ pull — точно ли подтянули
        $afterBehind = & git rev-list --count HEAD..origin/main 2>$null
        if ($beforeBehind -and [int]$beforeBehind -gt 0 -and [int]$afterBehind -gt 0) {
            Write-SyncLog "WARN: pull reported success but HEAD still behind by $afterBehind (something wrong)"
        }
        $tag = if ($pullResult.Attempts -gt 1) {
            "ok (after $($pullResult.Attempts) attempts, pulled $beforeBehind commit(s))"
        } elseif ([int]$beforeBehind -gt 0) {
            "ok (pulled $beforeBehind commit(s))"
        } else {
            "ok (already up to date)"
        }
        Write-SyncLog $tag
    }

    # --- Extras diff check (mcp-manifest.json vs .local-state/setup-extras.applied) ---
    # If manifest exists and either (a) marker missing or (b) marker hash != current
    # manifest hash -- log a notification line so user/Claude knows there is
    # pending extras setup. Doesn't try to auto-install (timeout + auto-classifier
    # + UX) -- only notifies. User runs setup-extras.ps1 manually when ready.
    $manifestFile = Join-Path $claudeDir 'mcp-manifest.json'
    $markerFile   = Join-Path $claudeDir '.local-state\setup-extras.applied'
    if (Test-Path $manifestFile) {
        $currentHash = (Get-FileHash $manifestFile -Algorithm SHA256).Hash
        $needsRun = $false
        $reason = ""
        if (-not (Test-Path $markerFile)) {
            $needsRun = $true
            $reason = "marker missing -- setup-extras never run on this machine"
        } else {
            try {
                $marker = Get-Content $markerFile -Raw | ConvertFrom-Json
                if ($marker.manifest_hash -ne $currentHash) {
                    $needsRun = $true
                    $reason = "manifest changed since last setup ($($marker.manifest_hash.Substring(0,8)) -> $($currentHash.Substring(0,8)))"
                }
            } catch {
                $needsRun = $true
                $reason = "marker unreadable"
            }
        }
        # Flag-файл для STOP-процедуры CLAUDE.md (тихая строка «запусти /sync-base»).
        # Создаём при pending, убираем при up-to-date. /sync-base снимает его после установки.
        $pendingFlag = Join-Path $claudeDir '.local-state\extras-pending.flag'
        if ($needsRun) {
            Write-SyncLog "extras-diff PENDING: $reason. Run: pwsh `"`$HOME\.claude\scripts\setup-extras.ps1`""
            $flagDir = Split-Path $pendingFlag -Parent
            if (-not (Test-Path $flagDir)) { New-Item -ItemType Directory -Path $flagDir -Force | Out-Null }
            Set-Content -Path $pendingFlag -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $reason" -Encoding UTF8
        } else {
            Write-SyncLog "extras-diff: up-to-date (manifest hash matches marker)"
            if (Test-Path $pendingFlag) { Remove-Item $pendingFlag -Force -ErrorAction SilentlyContinue }
        }
    }
    # === Merge shared settings → personal (Phase 1 sync-redesign 2026-05-21) ===
    # После успешного pull — вливаем shared values в local settings.json.
    # Идемпотентен: если ничего не изменилось, no-op.
    $mergeScript = Join-Path $claudeDir 'scripts\merge-shared-settings.ps1'
    if (Test-Path $mergeScript) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $mergeScript 2>&1 | Out-Null
    }
} catch {
    Write-SyncLog "exception: $_"
} finally {
    Pop-Location
    Write-SyncLog "DONE"
}

# Always exit 0 -- never block session start
exit 0
