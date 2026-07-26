param([switch]$KeepTmp)
$ErrorActionPreference = 'Stop'

$hookSource = Join-Path (Split-Path $PSScriptRoot -Parent) 'auto-push.ps1'
if (-not (Test-Path -LiteralPath $hookSource)) { throw 'auto-push hook not found' }

$tmp = Join-Path $env:TEMP ('auto-push-staged-safety-' + [guid]::NewGuid().ToString('N'))
$originalProfile = $env:USERPROFILE

function Invoke-Git([string]$dir, [string[]]$gitArgs) {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & git -C $dir @gitArgs 2>&1 | Out-Null
    $gitExit = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorAction
    if ($gitExit -ne 0) { throw "git $($gitArgs -join ' ') failed" }
}

try {
    $testHome = Join-Path $tmp 'home'
    $repo = Join-Path $testHome '.claude'
    $remote = Join-Path $tmp 'remote.git'
    New-Item -ItemType Directory -Path $repo -Force | Out-Null
    $repoScripts = Join-Path $repo 'scripts'
    New-Item -ItemType Directory -Path $repoScripts -Force | Out-Null
    $hook = Join-Path $repoScripts 'auto-push.ps1'
    Copy-Item -LiteralPath $hookSource -Destination $hook
    Invoke-Git $tmp @('init', '--bare', $remote)
    Invoke-Git $repo @('init', '-b', 'main')
    Invoke-Git $repo @('config', 'user.email', 'test@example.invalid')
    Invoke-Git $repo @('config', 'user.name', 'Auto Push Test')
    Invoke-Git $repo @('remote', 'add', 'origin', $remote)
    Set-Content -LiteralPath (Join-Path $repo 'CLAUDE.md') -Value 'base' -Encoding UTF8
    Invoke-Git $repo @('add', 'CLAUDE.md')
    Invoke-Git $repo @('commit', '-m', 'base')
    Invoke-Git $repo @('push', '-u', 'origin', 'main')
    New-Item -ItemType File -Path (Join-Path $repo '.developer-marker') | Out-Null

    Set-Content -LiteralPath (Join-Path $repo 'manual.txt') -Value 'manual staged work' -Encoding UTF8
    Invoke-Git $repo @('add', 'manual.txt')
    Set-Content -LiteralPath (Join-Path $repo 'CLAUDE.md') -Value 'managed hook work' -Encoding UTF8
    $before = (& git -C $repo rev-parse HEAD).Trim()

    $env:USERPROFILE = $testHome
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hook 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "hook exited $LASTEXITCODE" }

    $after = (& git -C $repo rev-parse HEAD).Trim()
    if ($after -ne $before) { throw 'hook committed pre-existing staged work' }
    $staged = & git -C $repo diff --cached --name-only
    if ($staged -ne 'manual.txt') { throw "staged index changed: $($staged -join ', ')" }
    $unstaged = & git -C $repo diff --name-only
    if ($unstaged -ne 'CLAUDE.md') { throw "managed work was not left unstaged: $($unstaged -join ', ')" }
    $log = Get-Content -LiteralPath (Join-Path $repo 'auto-sync.log') -Raw -Encoding UTF8
    if ($log -notmatch 'pre-existing staged changes') { throw 'safety skip was not logged' }
    Write-Host 'PASS auto-push preserves a pre-existing staged index'
} finally {
    $env:USERPROFILE = $originalProfile
    if (-not $KeepTmp) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
