<#
.SYNOPSIS
  Idempotent local-proxy / IPv4 fix for the revit-mcp-python MCP client (main.py).

.DESCRIPTION
  Upstream revit-mcp/revit-mcp-python ships main.py with REVIT_HOST="localhost" and
  httpx clients that honour HTTP_PROXY (trust_env=True). On corporate-proxy machines
  this routes even 127.0.0.1 requests through the proxy (-> empty 503 / hang), and
  "localhost" resolves to IPv6 ::1 first while pyRevit Routes listens on IPv4
  0.0.0.0:48884. This patch forces IPv4 and bypasses the proxy for the local bridge.
  Safe to re-run (idempotent). Применяется автоматически из setup-extras.ps1 после
  установки Revit-Connector; можно запускать вручную.
  Подробности: ~/.claude/memory/reference_revit_mcp.md, proxy_github.md.

.PARAMETER InstallDir
  revit-mcp-python install dir. Default: ~/.claude/mcp-servers/revit-mcp-python
#>
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE ".claude\mcp-servers\revit-mcp-python")
)
$ErrorActionPreference = "Stop"

$main = Join-Path $InstallDir "main.py"
if (-not (Test-Path $main)) {
    Write-Warning "[patch-revit-mcp] main.py not found: $main"
    return
}

$src  = Get-Content $main -Raw
$orig = $src

# 1) Force IPv4 host: Routes listens on IPv4 0.0.0.0; "localhost" -> IPv6 ::1 hangs.
$src = $src -replace 'REVIT_HOST\s*=\s*"localhost"', 'REVIT_HOST = "127.0.0.1"  # patched: force IPv4 (Routes on 0.0.0.0)'

# 2) trust_env=False on every httpx.AsyncClient(...) that lacks it:
#    skip corporate HTTP_PROXY for the local 127.0.0.1 bridge.
$src = [regex]::Replace($src, 'httpx\.AsyncClient\(([^)]*)\)', {
    param($m)
    $a = $m.Groups[1].Value
    if ($a -match 'trust_env') { return $m.Value }
    if ([string]::IsNullOrWhiteSpace($a)) { return 'httpx.AsyncClient(trust_env=False)' }
    return "httpx.AsyncClient($a, trust_env=False)"
})

if ($src -ne $orig) {
    # UTF-8 без BOM (main.py объявляет coding: utf-8)
    [System.IO.File]::WriteAllText($main, $src, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "[patch-revit-mcp] applied (IPv4 + trust_env=False): $main" -ForegroundColor Green
} else {
    Write-Host "[patch-revit-mcp] already patched / nothing to do: $main" -ForegroundColor Gray
}
