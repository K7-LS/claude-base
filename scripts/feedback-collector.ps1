<#
.SYNOPSIS
Собирает локальный feedback от consumer-ПК для Daniil'а (Phase 2 sync-redesign).

.DESCRIPTION
Запускается из auto-push.ps1 на ПК без .developer-marker (consumer mode).
Назначение — собрать структурированный feedback в формате который Daniil
потом ревью'ет и решает что внедрить в shared базу.

Workflow:

1. Сканирует ~/.claude/feedback-pending/*.md — файлы которые Claude
   написал в текущей сессии (если были error/suggestion/harvest finding).
2. Для каждого: добавляет metadata frontmatter (если нет) — hostname,
   user.email из git config, дата.
3. Перемещает в ~/.claude/feedback-staging/<yyyy-mm-dd>-<hostname>-<basename>.md.
4. Если ~/.claude/.feedback-config.json существует с github_repo — push'ит
   в branch feedback/<hostname-userprefix>. Если нет — оставляет
   локально в staging (Daniil заберёт вручную).

Claude в текущей сессии **сам** пишет feedback-pending/*.md когда
обнаруживает что что-то полезное надо передать Daniil'у (см. правило
"Feedback collection" в CLAUDE.md).

Идемпотентен: повторный запуск без новых pending = no-op.
#>

$ErrorActionPreference = 'Continue'

$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$PendingDir = Join-Path $ClaudeDir 'feedback-pending'
$StagingDir = Join-Path $ClaudeDir 'feedback-staging'
$ConfigFile = Join-Path $ClaudeDir '.feedback-config.json'
$LogFile = Join-Path $ClaudeDir 'auto-sync.log'

function Write-FbLog { param($msg)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] feedback-collector: $msg" |
        Add-Content -Path $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
}

# Identification — кто и откуда (для metadata frontmatter)
$hostname = $env:COMPUTERNAME
$userEmail = & git -C $ClaudeDir config user.email 2>$null
if (-not $userEmail) { $userEmail = 'unknown' }
$userPrefix = ($userEmail -split '@')[0]

# Ensure dirs exist
if (-not (Test-Path $StagingDir)) {
    New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
}
if (-not (Test-Path $PendingDir)) {
    New-Item -ItemType Directory -Path $PendingDir -Force | Out-Null
}

# === Auto-harvest session-reports от consumer-ПК (Phase 2-follow-up, 2026-05-26) ===
#
# Правило CLAUDE.md обязывает каждую сессию писать
# session-reports/<date>_<тема>/report.md. На consumer-ПК (без
# .developer-marker) auto-push.ps1 не пушит эти отчёты в claude-base/main
# (hub-and-spoke). Без этого блока отчёты копились локально и терялись
# для Daniil'а (см. R-090226727A 2026-05-26 — <разработчик> накопил 5 untracked
# отчётов за 5 дней, потом ошибочно git push origin main → revert).
#
# Логика:
# - Для каждого session-reports/<theme>/report.md проверяем tracked ли он
#   в git. Tracked = developer уже забрал в main, skip.
# - Untracked = consumer-side, кандидат на отправку.
# - Если файл с этим basename уже в feedback-staging/pushed/ — skip
#   (идемпотентность повторного запуска).
# - Иначе копируем в feedback-pending/report-<theme>.md, штатный flow
#   ниже добавит frontmatter, перенесёт в staging, push'нёт через
#   GitHub API в claude-base-feedback ветку feedback/<host>-<user>.
$SessionReportsDir = Join-Path $ClaudeDir 'session-reports'
$PushedDir = Join-Path $StagingDir 'pushed'

if (Test-Path $SessionReportsDir) {
    $reports = @(Get-ChildItem $SessionReportsDir -Directory -ErrorAction SilentlyContinue)
    $harvestedCount = 0

    foreach ($reportDir in $reports) {
        $reportFile = Join-Path $reportDir.FullName 'report.md'
        if (-not (Test-Path $reportFile)) { continue }

        # Идемпотентность 1: tracked в git → developer уже забрал в main.
        # ls-files --error-unmatch exit 0 = tracked, exit ≠ 0 = untracked.
        $relPath = "session-reports/$($reportDir.Name)/report.md"
        & git -C $ClaudeDir ls-files --error-unmatch -- $relPath 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { continue }

        # Идемпотентность 2: уже pushed в этой machine?
        # Формат имени в pushed/: <ts>-<HOST>-<user>-report-<theme>.md
        $basename = "report-$($reportDir.Name)"
        if (Test-Path $PushedDir) {
            $existing = @(Get-ChildItem $PushedDir -File -Filter "*-${basename}.md" -ErrorAction SilentlyContinue)
            if ($existing.Count -gt 0) { continue }
        }

        # Идемпотентность 3: уже в pending (этой же сессией)?
        $pendingTarget = Join-Path $PendingDir "${basename}.md"
        if (Test-Path $pendingTarget) { continue }

        # Копируем — штатный flow возьмёт дальше.
        Copy-Item $reportFile $pendingTarget -Force
        $harvestedCount++
    }

    if ($harvestedCount -gt 0) {
        Write-FbLog "auto-harvested $harvestedCount untracked session-report(s) → feedback-pending/"
    }
}

$pendingFiles = @(Get-ChildItem $PendingDir -File -Filter '*.md' -ErrorAction SilentlyContinue)
if ($pendingFiles.Count -eq 0) {
    Write-FbLog "feedback-pending/ empty — nothing to collect"
    exit 0
}

Write-FbLog "found $($pendingFiles.Count) pending feedback file(s)"

$now = Get-Date -Format 'yyyy-MM-dd_HHmm'

foreach ($f in $pendingFiles) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8

    # Добавляем frontmatter если его нет
    if ($content -notmatch '(?s)^---\s*\r?\n') {
        $frontmatter = @"
---
collected: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')
hostname: $hostname
user: $userEmail
basename: $($f.BaseName)
---

"@
        $content = $frontmatter + $content
    }

    # Move to staging с уникальным именем
    $newName = "${now}-${hostname}-${userPrefix}-$($f.BaseName).md"
    $destPath = Join-Path $StagingDir $newName

    [System.IO.File]::WriteAllText($destPath, $content, [System.Text.UTF8Encoding]::new($false))
    Remove-Item $f.FullName -Force

    Write-FbLog "staged: $newName"
}

# === Remote push в private feedback-репо через GitHub API (Phase 2-follow-up) ===
#
# Конфиг ~/.claude/.feedback-config.json (gitignored, per-PC) формат:
# {
#   "github_repo": "K7-LS/claude-base-feedback",
#   "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxx",  // PAT с repo scope
#   "branch": "feedback/${hostname}-${userprefix}"  // optional; default below
# }
#
# Если конфиг отсутствует — файлы остаются в staging локально, Daniil
# забирает вручную (USB/mail/shared folder).
#
if (-not (Test-Path $ConfigFile)) {
    Write-FbLog "no .feedback-config.json — feedback staged locally. Daniil заберёт вручную."
    exit 0
}

try {
    $cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-FbLog "WARN: .feedback-config.json invalid JSON: $_"
    exit 0
}

if (-not $cfg.github_repo) {
    Write-FbLog "WARN: .feedback-config.json missing github_repo. Skipping remote push."
    exit 0
}

# === DPAPI decrypt (2026-05-26) ===
# Приоритет: token_encrypted (зашифрован через scripts/Set-FeedbackToken.ps1)
# > token (legacy plaintext, оставлен для backward compat пока сотрудники
# не мигрировали через Set-FeedbackToken.ps1).
#
# token_encrypted шифруется DPAPI CurrentUser scope — расшифровать может
# ТОЛЬКО тот же Windows-пользователь на той же машине. Защищает от
# случайной утечки .feedback-config.json в git / в чат-историю / в логи.
$token = $null
if ($cfg.token_encrypted) {
    try {
        $secStr = ConvertTo-SecureString -String $cfg.token_encrypted -ErrorAction Stop
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secStr)
        $token = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    } catch {
        Write-FbLog "WARN: token_encrypted не расшифровывается (другой user/machine?). Запустить scripts/Set-FeedbackToken.ps1 на этом ПК."
        exit 0
    }
} elseif ($cfg.token) {
    Write-FbLog "WARN: .feedback-config.json использует plain token (legacy). Рекомендуется запустить scripts/Set-FeedbackToken.ps1 для шифрования через DPAPI."
    $token = $cfg.token
} else {
    Write-FbLog "WARN: .feedback-config.json missing both token_encrypted and token. Skipping remote push."
    exit 0
}

# Default branch name если не задан
$branch = if ($cfg.branch) { $cfg.branch } else { "feedback/${hostname}-${userPrefix}" }
$repo = $cfg.github_repo

# Каталог для уже-push'нутых файлов
$PushedDir = Join-Path $StagingDir 'pushed'
if (-not (Test-Path $PushedDir)) {
    New-Item -ItemType Directory -Path $PushedDir -Force | Out-Null
}

# Получить SHA текущего HEAD branch (или main если branch ещё не существует)
function Get-BranchHeadSha {
    param([string]$Repo, [string]$Branch, [string]$Token)
    $headers = @{
        Authorization = "token $Token"
        Accept = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }
    try {
        $resp = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/git/refs/heads/$Branch" `
            -Headers $headers -Method Get -ErrorAction Stop
        return $resp.object.sha
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) {
            # Branch не существует — создадим от main
            $mainResp = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/git/refs/heads/main" `
                -Headers $headers -Method Get -ErrorAction Stop
            $createBody = @{
                ref = "refs/heads/$Branch"
                sha = $mainResp.object.sha
            } | ConvertTo-Json
            Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/git/refs" `
                -Headers $headers -Method Post -Body $createBody -ContentType 'application/json' -ErrorAction Stop | Out-Null
            Write-FbLog "created branch '$Branch' от main"
            return $mainResp.object.sha
        }
        throw
    }
}

# Push один файл через PUT /contents API
function Push-FeedbackFile {
    param(
        [string]$Repo,
        [string]$Branch,
        [string]$Token,
        [string]$LocalPath,
        [string]$RemotePath
    )
    $headers = @{
        Authorization = "token $Token"
        Accept = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }
    $bytes = [System.IO.File]::ReadAllBytes($LocalPath)
    $contentB64 = [Convert]::ToBase64String($bytes)
    $msg = "feedback: $(Split-Path $LocalPath -Leaf) from $env:COMPUTERNAME"

    # Проверить — существует ли уже файл (нужен SHA для update)
    $sha = $null
    try {
        $existing = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/contents/$RemotePath`?ref=$Branch" `
            -Headers $headers -Method Get -ErrorAction Stop
        $sha = $existing.sha
    } catch {
        # 404 — файла нет, это новый create
    }

    $body = @{
        message = $msg
        content = $contentB64
        branch = $Branch
    }
    if ($sha) { $body.sha = $sha }
    $bodyJson = $body | ConvertTo-Json -Depth 5

    Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/contents/$RemotePath" `
        -Headers $headers -Method Put -Body $bodyJson -ContentType 'application/json' -ErrorAction Stop | Out-Null
}

# Список файлов в staging для push (исключая pushed/)
$toPush = @(Get-ChildItem $StagingDir -File -Filter '*.md' -ErrorAction SilentlyContinue)
if ($toPush.Count -eq 0) {
    Write-FbLog "no staged files to push to $repo"
    exit 0
}

Write-FbLog "pushing $($toPush.Count) file(s) to $repo branch=$branch"

# Гарантируем что branch существует
try {
    Get-BranchHeadSha -Repo $repo -Branch $branch -Token $token | Out-Null
} catch {
    Write-FbLog "FAILED to ensure branch '$branch' exists: $_"
    exit 0
}

$pushedCount = 0
foreach ($file in $toPush) {
    $remotePath = "feedback/$($file.Name)"
    try {
        Push-FeedbackFile -Repo $repo -Branch $branch -Token $token `
            -LocalPath $file.FullName -RemotePath $remotePath
        # Переместить в pushed/
        Move-Item $file.FullName (Join-Path $PushedDir $file.Name) -Force
        $pushedCount++
        Write-FbLog "pushed: $($file.Name)"
    } catch {
        Write-FbLog "FAILED push $($file.Name): $_"
    }
}

Write-FbLog "remote push complete: $pushedCount/$($toPush.Count) files to $repo / $branch"
exit 0
