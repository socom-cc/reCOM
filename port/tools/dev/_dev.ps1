# _dev.ps1: shared helpers for the port/tools/dev PowerShell scripts (dot-sourced; Windows only).
#   $SocomRepo                 checkout root, derived from this file's location
#   Get-SocomScratch           $env:SOCOM_SCRATCH (absolute or repo-relative), default build\port\dev
#   Get-SocomPcsx2             $env:SOCOM_PCSX2: the PCSX2 executable or the folder holding pcsx2-qt.exe
#   Get-SocomDisc              $env:SOCOM_DISC_IMAGE: the game disc image (user-local)
#   Get-SocomWslArgs           wsl.exe arguments selecting $env:SOCOM_WSL_DISTRO (default distribution)
#   ConvertTo-SocomWslPath     a Windows path in its Linux (WSL) form, via wslpath
#   Invoke-SocomWsl <script> [args]  run a bash script in WSL, passing the SOCOM_* variables below
# Emulator, disc image and BIOS paths are user-local: set them in your own shell or profile, never in
# a tracked file.
$SocomRepo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path

function Get-SocomScratch {
    $s = $env:SOCOM_SCRATCH
    if (-not $s) { $s = 'build\port\dev' }
    if (-not [System.IO.Path]::IsPathRooted($s)) { $s = Join-Path $SocomRepo $s }
    New-Item -ItemType Directory -Force $s | Out-Null
    (Resolve-Path $s).Path
}

function Get-SocomPcsx2 {
    $p = $env:SOCOM_PCSX2
    if (-not $p) { throw 'SOCOM_PCSX2 is not set (path to pcsx2-qt.exe or its folder)' }
    if (Test-Path $p -PathType Container) {
        $exe = Get-ChildItem $p -Filter 'pcsx2*.exe' -File -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
        if (-not $exe) { throw "SOCOM_PCSX2 folder has no pcsx2*.exe: $p" }
        return $exe.FullName
    }
    if (-not (Test-Path $p -PathType Leaf)) { throw "SOCOM_PCSX2 does not exist: $p" }
    (Resolve-Path $p).Path
}

function Get-SocomDisc {
    $d = $env:SOCOM_DISC_IMAGE
    if (-not $d) { throw 'SOCOM_DISC_IMAGE is not set (path to the game disc image)' }
    if (-not (Test-Path $d -PathType Leaf)) { throw "SOCOM_DISC_IMAGE does not exist (drive not attached?): $d" }
    (Resolve-Path $d).Path
}

function Get-SocomWslArgs {
    if ($env:SOCOM_WSL_DISTRO) { return @('-d', $env:SOCOM_WSL_DISTRO) }
    @()
}

function ConvertTo-SocomWslPath([string]$Path) {
    $w = Get-SocomWslArgs
    $full = [System.IO.Path]::GetFullPath($Path) -replace '\\', '/'
    $ErrorActionPreference = 'Continue'
    ((& wsl.exe @w -e wslpath -u $full) 2>$null | Select-Object -First 1).Trim()
}

function Invoke-SocomWsl([string]$Script, [string[]]$Arguments = @()) {
    # Forward the dev variables into WSL (WSLENV), untranslated; env.sh converts Windows paths.
    $names = 'SOCOM_SCRATCH', 'SOCOM_NAME', 'SOCOM_TREE', 'SOCOM_ELF', 'SOCOM_PS2DEV', 'TREE', 'SHARED', 'STUBCMD', 'N'
    $fwd = ($names | Where-Object { Test-Path "env:$_" } | ForEach-Object { "$_/u" }) -join ':'
    $old = $env:WSLENV
    if ($fwd) { $env:WSLENV = (@($old, $fwd) | Where-Object { $_ }) -join ':' }
    try {
        $w = Get-SocomWslArgs
        $lin = ConvertTo-SocomWslPath $Script
        $ErrorActionPreference = 'Continue'
        & wsl.exe @w -e bash $lin @Arguments 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'Failed to translate' }
    } finally { $env:WSLENV = $old }
}
