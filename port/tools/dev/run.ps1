param(
    [Parameter(Mandatory = $true)][string]$Build,   # WSL build dir name under ~/.cache/socom
    [Parameter(Mandatory = $true)][string]$Name,    # run name: <scratch>\<Name>.elf/.log/.run.txt/-<t>.png
    [int]$Seconds = 100,                            # kill PCSX2 after this many seconds
    [string]$Shots = ""                             # screenshot times, e.g. "60,90"; empty = one at -Seconds
)
# run.ps1: copy a test build's ELF out of WSL into the scratch folder ($env:SOCOM_SCRATCH, default
# build\port\dev) as <Name>.elf and boot it once through pcsx2-boot.ps1 (second monitor, never takes
# focus, quiet). The log is <Name>.log, screenshots <Name>-<t>.png, the helper's report
# <Name>.run.txt (its first lines are printed). Merges the per-worker run.ps1 / go.ps1.
. (Join-Path $PSScriptRoot '_dev.ps1')
$dir = Get-SocomScratch
$elf = Join-Path $dir "$Name.elf"
if (Test-Path $elf) { Remove-Item $elf }
$welf = ConvertTo-SocomWslPath $elf
$w = Get-SocomWslArgs
$ErrorActionPreference = 'Continue'
& wsl.exe @w -e bash -c "cp `"`$HOME/.cache/socom/$Build/socom_port.elf`" '$welf'" 2>$null
if (-not (Test-Path $elf)) { "no ELF in ~/.cache/socom/$Build (build it first)"; exit 1 }
$report = Join-Path $dir "$Name.run.txt"
& (Join-Path $PSScriptRoot 'pcsx2-boot.ps1') -Elf $elf -Log (Join-Path $dir "$Name.log") -Seconds $Seconds -Shots $Shots -ShotPrefix (Join-Path $dir $Name) | Out-File -Encoding utf8 $report
Get-Content $report | Select-Object -First 3
