# Обёртка SessionStart-уведомления о релизах claude-base v2 (2026-08-28).
# Прежний хук указывал прямо на base\runtime\hooks\check-release.ps1 —
# на ПК без установленного релизного слоя файла нет, и владелец никогда
# не узнавал о существовании обновлений (блокер №3 ревизии sync-base).
# Обёртка: релизный слой есть — делегирует штатному хуку; нет — лёгкая
# анонимная проверка последнего релиза через connection-runtime скилла
# sync-base (он приезжает git'ом) с TTL 24 часа.
$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8NoBom

$claudeDir = Join-Path $env:USERPROFILE '.claude'
$installedHook = Join-Path $claudeDir 'base\runtime\hooks\check-release.ps1'
if (Test-Path -LiteralPath $installedHook -PathType Leaf) {
    & $installedHook
    exit $LASTEXITCODE
}

try {
    $connection = Join-Path $claudeDir 'skills\sync-base\runtime\connection.ps1'
    if (-not (Test-Path -LiteralPath $connection -PathType Leaf)) { exit 0 }

    $stateDir = Join-Path $claudeDir '.local-state'
    $statePath = Join-Path $stateDir 'check-release-fallback.json'
    $now = [DateTimeOffset]::UtcNow
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        try {
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 |
                ConvertFrom-Json
            $checked = [DateTimeOffset]::Parse([string]$state.checked_at)
            if (($now - $checked).TotalHours -lt 24) { exit 0 }
        } catch {
            # повреждённый TTL-файл заменит следующая успешная проверка
        }
    }

    . $connection
    $releases = Invoke-WithLlmConnection `
        -HomePath $env:USERPROFILE `
        -ScriptBlock {
            Invoke-LlmJsonGet `
                -Uri 'https://api.github.com/repos/K7-LS/claude-base-v2/releases?per_page=20' `
                -UserAgent 'claude-base-v2-version-check/1' `
                -TimeoutSeconds 5
        }
    $stable = @($releases) |
        Where-Object {
            (-not $_.draft) -and (-not $_.prerelease) -and
            ([string]$_.tag_name -match '^claude-v\d+\.\d+\.\d+$')
        } |
        Sort-Object -Property published_at -Descending |
        Select-Object -First 1

    [IO.Directory]::CreateDirectory($stateDir) | Out-Null
    $payload = [ordered]@{
        checked_at = $now.ToString('o')
        latest_tag = if ($stable) { [string]$stable.tag_name } else { $null }
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($statePath, $payload + "`n",
        (New-Object Text.UTF8Encoding($false)))

    if ($stable) {
        $latest = ([string]$stable.tag_name) -replace '^claude-v', ''
        [ordered]@{
            systemMessage = (
                "Claude-base $latest доступен; релизный слой на этом ПК не " +
                'установлен. Обновление: $sync-base (скилл уже в базе).'
            )
        } | ConvertTo-Json -Compress
    }
} catch {
    # проверка уведомления никогда не блокирует старт сессии
}
exit 0
