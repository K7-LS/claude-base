param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$OpenCodeArgs
)

$env:OPENCODE_DISABLE_CLAUDE_CODE = '1'
$env:OPENCODE_DISABLE_CLAUDE_CODE_PROMPT = '1'
$env:OPENCODE_DISABLE_CLAUDE_CODE_SKILLS = '1'

& opencode @OpenCodeArgs
exit $LASTEXITCODE
