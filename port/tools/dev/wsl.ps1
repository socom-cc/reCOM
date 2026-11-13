# wsl.ps1 <script> [args...]: run one of the Linux-side dev scripts (tree.sh, fake.sh, hook.sh,
# tb.sh, default.sh, a test-hook build.sh, ...) in WSL from PowerShell, e.g.
#   .\port\tools\dev\wsl.ps1 tb.sh -k stance stc1 pad_s1.txt
#   .\port\tools\dev\wsl.ps1 port\test-hooks\stance\build.sh stc1
# A bare name is looked up in port/tools/dev; other paths are taken as given (or repo-relative).
# SOCOM_SCRATCH, SOCOM_NAME, SOCOM_TREE, SOCOM_ELF, SOCOM_PS2DEV, TREE, SHARED, STUBCMD and N are
# forwarded; the distribution is $env:SOCOM_WSL_DISTRO (default: WSL's default distribution).
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Script,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @()
)
. (Join-Path $PSScriptRoot '_dev.ps1')
$path = $Script
if (-not (Test-Path $path)) {
    $cands = @((Join-Path $PSScriptRoot $Script), (Join-Path $SocomRepo $Script))
    $path = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $path) { Write-Error "wsl.ps1: script not found: $Script"; exit 2 }
Invoke-SocomWsl (Resolve-Path $path).Path $Rest
