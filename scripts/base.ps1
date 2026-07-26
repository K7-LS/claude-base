param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BaseArgs
)

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error 'Python не найден. Укажи доверенный Python в PATH.'
    exit 2
}

& $python.Source (Join-Path $PSScriptRoot 'base_cli.py') @BaseArgs
exit $LASTEXITCODE
