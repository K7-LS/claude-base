$ErrorActionPreference = 'Stop'

$scripts = Split-Path $PSScriptRoot -Parent
$autoPullSource = Join-Path $scripts 'auto-pull.ps1'
$autoPushSource = Join-Path $scripts 'auto-push.ps1'
$tmp = Join-Path $env:TEMP ('one-way-sync-' + [guid]::NewGuid().ToString('N'))
$fakeHome = Join-Path $tmp 'user'
$fakeClaude = Join-Path $fakeHome '.claude'
$fakeBin = Join-Path $tmp 'bin'
$gitLog = Join-Path $tmp 'git.log'
$pushState = Join-Path $tmp 'push-disabled.flag'

try {
    New-Item -ItemType Directory -Path (Join-Path $fakeClaude '.git') -Force | Out-Null
    $fakeScripts = Join-Path $fakeClaude 'scripts'
    New-Item -ItemType Directory -Path $fakeScripts -Force | Out-Null
    New-Item -ItemType Directory -Path $fakeBin -Force | Out-Null
    $autoPull = Join-Path $fakeScripts 'auto-pull.ps1'
    $autoPush = Join-Path $fakeScripts 'auto-push.ps1'
    Copy-Item -LiteralPath $autoPullSource -Destination $autoPull
    Copy-Item -LiteralPath $autoPushSource -Destination $autoPush

    $shim = @'
@echo off
echo %*>>"%FAKE_GIT_LOG%"
if "%1 %2 %3"=="remote get-url origin" (
  echo https://example.invalid/base.git
  exit /b 0
)
if "%1 %2 %3 %4"=="remote get-url --push origin" (
  if exist "%FAKE_PUSH_STATE%" (
    echo NO_PUSH_CONSUMER
  ) else (
    echo https://example.invalid/base.git
  )
  exit /b 0
)
if "%1 %2 %3 %4 %5"=="remote set-url --push origin NO_PUSH_CONSUMER" (
  type nul >"%FAKE_PUSH_STATE%"
  exit /b 0
)
if "%1 %2 %3"=="config --global --get" exit /b 0
if "%1"=="rev-list" (
  echo 0
  exit /b 0
)
exit /b 0
'@
    Set-Content -LiteralPath (Join-Path $fakeBin 'git.cmd') -Value $shim -Encoding Ascii

    $oldUserProfile = $env:USERPROFILE
    $oldPath = $env:PATH
    $oldGitLog = $env:FAKE_GIT_LOG
    $oldPushState = $env:FAKE_PUSH_STATE
    $env:USERPROFILE = $fakeHome
    $env:PATH = $fakeBin + [IO.Path]::PathSeparator + $oldPath
    $env:FAKE_GIT_LOG = $gitLog
    $env:FAKE_PUSH_STATE = $pushState

    & powershell -NoProfile -ExecutionPolicy Bypass -File $autoPull | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "auto-pull exit=$LASTEXITCODE" }
    $pullCalls = @(Get-Content -LiteralPath $gitLog -ErrorAction SilentlyContinue)
    if (-not ($pullCalls -match '^remote set-url --push origin NO_PUSH_CONSUMER$')) {
        throw 'consumer auto-pull did not disable origin push URL'
    }

    Remove-Item -LiteralPath $gitLog -Force
    & powershell -NoProfile -ExecutionPolicy Bypass -File $autoPush | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "auto-push exit=$LASTEXITCODE" }
    $pushCalls = @(Get-Content -LiteralPath $gitLog -ErrorAction SilentlyContinue)
    if ($pushCalls.Count -ne 0) {
        throw "consumer auto-push invoked git: $($pushCalls -join '; ')"
    }

    $log = Get-Content -LiteralPath (Join-Path $fakeClaude 'auto-sync.log') -Raw
    if ($log -notmatch 'consumer read-only') {
        throw 'consumer no-op was not recorded'
    }
    Write-Host 'PASS one-way hub-to-consumer sync contract'
} finally {
    $env:USERPROFILE = $oldUserProfile
    $env:PATH = $oldPath
    $env:FAKE_GIT_LOG = $oldGitLog
    $env:FAKE_PUSH_STATE = $oldPushState
    if (Test-Path -LiteralPath $tmp) {
        Remove-Item -LiteralPath $tmp -Recurse -Force
    }
}
