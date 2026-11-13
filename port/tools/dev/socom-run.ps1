param(
    [switch]$WorkingTree,   # build the working tree (includes uncommitted worker edits) instead of HEAD
    [switch]$SkipBuild,     # boot the last socom-run build without rebuilding
    [switch]$Monitor2,      # open PCSX2 on the secondary monitor
    [switch]$NoLaunch       # build only, don't start PCSX2
)
# Play launcher: builds the normal port ELF (no test hooks, no fake pad) from the last commit's src/
# and port/ (or the working tree with -WorkingTree) into its own WSL build dir
# (~/.cache/socom/play), then boots it in PCSX2 (GUI, left running) with your disc image.
# Needs $env:SOCOM_PCSX2 and $env:SOCOM_DISC_IMAGE (user-local); $env:SOCOM_WSL_DISTRO picks the
# WSL distribution. Session logs: build\port\play\last-run.log (previous: last-run.prev.log).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_dev.ps1')
$Repo    = $SocomRepo
$WslSrc  = '$HOME/.cache/socom/play-src'     # synced copy of src/ + port/
$WslBld  = '$HOME/.cache/socom/play'         # build dir used only by socom-run
$PlayDir = Join-Path $Repo 'build\port\play'
if (-not $NoLaunch) {
    try { $Pcsx2 = Get-SocomPcsx2; $Disc = Get-SocomDisc } catch { "$($_.Exception.Message)"; exit 1 }
}

function Wsl([string]$cmd) {
    # wsl.exe prints harmless "Failed to translate" PATH warnings on stderr; don't let them stop the script
    $ErrorActionPreference = 'Continue'
    $w = Get-SocomWslArgs
    & wsl.exe @w -e bash -c $cmd 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch 'Failed to translate' }
}

if (-not $SkipBuild) {
    if ($WorkingTree) {
        $what = 'working tree'
        $r = ConvertTo-SocomWslPath $Repo
        $sync = "mkdir -p $WslSrc && rsync -a --checksum --delete '$r/src/' $WslSrc/src/ && rsync -a --checksum --delete '$r/port/' $WslSrc/port/"
    } else {
        $head = (& git -C $Repo log -1 --format='%h %s').Trim()
        $what = "commit $head"
        $tar = Join-Path $env:TEMP 'socom-run-src.tar'
        # core.autocrlf=false: export the stored LF files (CRLF breaks link.sh under bash)
        & git -C $Repo -c core.autocrlf=false archive --format=tar -o $tar HEAD src port
        if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
        $wtar = ConvertTo-SocomWslPath $tar
        $sync = "rm -rf ${WslSrc}.stage && mkdir -p ${WslSrc}.stage $WslSrc && tar -xf '$wtar' -C ${WslSrc}.stage && rsync -a --checksum --delete ${WslSrc}.stage/ $WslSrc/ && rm -rf ${WslSrc}.stage"
    }
    "Building the normal game (no test hooks) from the $what ..."
    Wsl $sync | Out-Null
    $out = Wsl "env SOCOM_PORT_BUILD=$WslBld bash $WslSrc/port/tools/link.sh"
    $out | Select-String 'library:|link:' | ForEach-Object { $_.Line }
    if (-not ($out -match 'link: exit=0 undefined=0 multiple=0')) {
        "BUILD FAILED - not launching. Logs: lib.log and link.log in the WSL dir ~/.cache/socom/play"
        exit 1
    }
}

New-Item -ItemType Directory -Force $PlayDir | Out-Null
$copy = Join-Path $PlayDir 'socom_port.elf'
if (-not $SkipBuild -or -not (Test-Path $copy)) {
    $wcopy = ConvertTo-SocomWslPath $copy
    Wsl "test -f $WslBld/socom_port.elf && cp $WslBld/socom_port.elf '$wcopy'" | Out-Null
}
if ($NoLaunch) { "Built; not launching (-NoLaunch)."; exit 0 }
if (-not (Test-Path $copy)) { "No socom-run build yet; run without -SkipBuild first."; exit 1 }
# Log every session (the port's [socom-port] traces and STOP lines) to build\port\play\last-run.log;
# the previous one is kept as last-run.prev.log.
$log = Join-Path $PlayDir 'last-run.log'
if (Test-Path $log) { Move-Item $log (Join-Path $PlayDir 'last-run.prev.log') -Force }
$p = Start-Process -FilePath $Pcsx2 -PassThru -ArgumentList @('-fastboot', '-earlyconsolelog', '-logfile', "`"$log`"", '-elf', "`"$copy`"", '--', "`"$Disc`"")
# Test runs turn their PCSX2 down to 15% in the Windows mixer; make sure this session is at the
# normal level in case Windows carried that over (PCSX2's own volume setting still applies).
$vol = Join-Path $PSScriptRoot 'set-appvolume.ps1'
if (Test-Path $vol) { Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$vol`"", '-ProcessId', $p.Id, '-Level', '1.0' | Out-Null }
if ($Monitor2) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -Name W -Namespace SocomRun -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);'
    $s = [System.Windows.Forms.Screen]::AllScreens | Where-Object { -not $_.Primary } | Select-Object -First 1
    for ($i = 0; $i -lt 200 -and $p.MainWindowHandle -eq 0; $i++) { Start-Sleep -Milliseconds 50; $p.Refresh() }
    if ($s -and $p.MainWindowHandle -ne 0) { [SocomRun.W]::SetWindowPos($p.MainWindowHandle, [IntPtr]::Zero, $s.WorkingArea.X + 20, $s.WorkingArea.Y + 20, 0, 0, 0x15) | Out-Null }
}
"Launched PCSX2 (pid $($p.Id)) with the build from $(if ($SkipBuild) { 'the last socom-run' } else { $what })."
