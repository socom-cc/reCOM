# dx.ps1 <start> [end|+len]: annotated disassembly of support/socom.elf (read-only): dis.sh in WSL,
# then disx.py (lui/addiu, $gp-relative symbols and strings). <end> defaults to the symbol size at
# <start> (0x400 when there is no sized symbol).
param([Parameter(Mandatory = $true)][string]$Start, [string]$End = "")
. (Join-Path $PSScriptRoot '_dev.ps1')
$a = [Convert]::ToInt64($Start.Replace("0x", ""), 16)
if ($End -eq "") {
    $size = [int](python (Join-Path $PSScriptRoot 'symsize.py') ("0x{0:x}" -f $a))
    $End = "0x{0:x}" -f ($a + $size)
} elseif ($End.StartsWith("+")) {
    $End = "0x{0:x}" -f ($a + [Convert]::ToInt64($End.Substring(1).Replace("0x", ""), 16))
}
Invoke-SocomWsl (Join-Path $PSScriptRoot 'dis.sh') @($Start, $End) | python (Join-Path $PSScriptRoot 'disx.py')
