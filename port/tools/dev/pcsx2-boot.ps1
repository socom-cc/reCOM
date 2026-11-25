param(
    [Parameter(Mandatory = $true)][string]$Elf,       # Windows path to the ELF to boot (copy it out of WSL first; run.ps1 does)
    [Parameter(Mandatory = $true)][string]$Log,       # PCSX2 log file
    [int]$Seconds = 40,                               # kill PCSX2 after this many seconds
    [string]$Shots = "",                              # screenshot times in seconds, e.g. "20,35"; empty = one at -Seconds
    [string]$ShotPrefix = "",                         # screenshot path without extension; empty = next to the log
    [switch]$CloseCardDialog,                         # close PCSX2's "Memory Card Read Failed" dialog (default: leave it open)
    [string]$MemCard = "",                            # a card file of the portable profile's memcards folder, in slot 1 for this run only
    [string]$DonePattern = "",                        # regex: end the run early once the log has it -DoneCount times
    [int]$DoneCount = 1,
    [int]$DoneExtra = 5,                              # seconds to keep running after that
    [string]$GameArgs = ""                            # the game's command line (PCSX2 -gameargs), e.g. "-f"; empty = none
)
# Shared PCSX2 boot helper for port test runs. The emulator and the disc image come from
# $env:SOCOM_PCSX2 (pcsx2-qt.exe or its folder) and $env:SOCOM_DISC_IMAGE; both are user-local.
# The user works on the primary monitor, so this:
#   - moves the PCSX2 window to the secondary monitor as soon as it exists,
#   - never activates it, and hands focus back to whatever window the user had,
#   - captures screenshots with PrintWindow (works while the window is covered),
#     falling back to a screen copy only if PrintWindow returns an all-black image.
. (Join-Path $PSScriptRoot '_dev.ps1')
try { $pcsx2 = Get-SocomPcsx2; $disc = Get-SocomDisc } catch { "$($_.Exception.Message)"; exit 1 }
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public struct PRECT { public int Left, Top, Right, Bottom; }
public static class PcsxWin {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out PRECT r);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
  [DllImport("user32.dll", EntryPoint = "GetWindowThreadProcessId")] static extern uint GetWindowPid(IntPtr h, out uint pid);
  public static uint OwnerPid(IntPtr h) { uint pid = 0; if (h != IntPtr.Zero) GetWindowPid(h, out pid); return pid; }
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  // Close this process's windows with the given title (WM_CLOSE); returns how many.
  public static int CloseTitled(uint pid, string title) {
    int n = 0;
    EnumWindows((h, l) => { if (OwnerPid(h) == pid && Title(h) == title) { PostMessage(h, 0x0010, IntPtr.Zero, IntPtr.Zero); n++; } return true; }, IntPtr.Zero);
    return n;
  }
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
  public static string Title(IntPtr h) { var sb = new System.Text.StringBuilder(256); GetWindowText(h, sb, 256); return sb.ToString(); }
  public static void GiveBack(IntPtr prev) {
    if (prev == IntPtr.Zero) return;
    uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
    uint me = GetCurrentThreadId();
    AttachThreadInput(me, fg, true);
    SetForegroundWindow(prev);
    AttachThreadInput(me, fg, false);
  }
}
"@
$SWP_NOSIZE = 0x1; $SWP_NOZORDER = 0x4; $SWP_NOACTIVATE = 0x10
$screen = [System.Windows.Forms.Screen]::AllScreens | Where-Object { -not $_.Primary } | Select-Object -First 1
if (-not $screen) { $screen = [System.Windows.Forms.Screen]::PrimaryScreen }
$area = $screen.WorkingArea

# Close test runs left behind by an earlier call that was cut off before its kill step:
# only PCSX2 started in batch mode (test runs; the user's own play sessions don't use -batch)
# and older than 30 minutes. Each run's own watchdog (below) already ends it at -Seconds + 30, so
# this is only for a watchdog that died; the limit must stay longer than the longest test run
# (the 12-minute round trip), or one worker's boot closes another worker's run.
Get-CimInstance Win32_Process -Filter "Name = 'pcsx2-qt.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*-batch*' -and ((Get-Date) - $_.CreationDate).TotalMinutes -gt 30 } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "closed stale test run $($_.ProcessId)" }

$prev = [PcsxWin]::GetForegroundWindow()
if (Test-Path $Log) { Remove-Item $Log }
# $env:SOCOM_PCSX2_PORTABLE = 1 (user-local, like the paths): test runs use PCSX2's portable
# profile (-portable: settings, memory cards and so on in the emulator's own folder) instead of
# the user's own profile. The portable profile is set up once by the user; with empty memory-card
# slots there, test runs never touch or lock the user's cards.
$pargs = @('-nogui', '-batch', '-fastboot', '-earlyconsolelog')
$portable = [bool]($env:SOCOM_PCSX2_PORTABLE -and $env:SOCOM_PCSX2_PORTABLE -ne '0')
$gameIni = $null
if ($portable) {
    $pargs = @('-portable') + $pargs
    # Memory cards, per run. PCSX2 looks for game settings under the ELF's CRC (the XOR of the
    # file's 32-bit words: "tried '...\gamesettings\<CRC>.ini'" in its log), so this run gets its
    # own settings file there, removed again when the run ends: both card slots EMPTY, whatever
    # the profile's own slots say, unless -MemCard names a card file of the portable profile's
    # memcards folder: then that card is in slot 1, for this run only. So test runs never share
    # a card, and only a run that asks for one (the save / load test) touches it.
    $gsDir = Join-Path (Split-Path $pcsx2) 'gamesettings'
    # The only card a test run may hold is the dedicated test card the user named in
    # SOCOM_TEST_MEMCARD (user-local, like the emulator path): any other name is refused, so a
    # test build that may format a card can never be given another one.
    if ($MemCard -ne "" -and (-not $env:SOCOM_TEST_MEMCARD -or $MemCard -ne $env:SOCOM_TEST_MEMCARD)) { "-MemCard refused: '$MemCard' is not the dedicated test card (SOCOM_TEST_MEMCARD)"; exit 1 }
    if ($MemCard -ne "" -and -not (Test-Path (Join-Path (Join-Path (Split-Path $pcsx2) 'memcards') $MemCard))) { "memory card not found in the portable profile: $MemCard"; exit 1 }
    $bytes = [System.IO.File]::ReadAllBytes($Elf)
    $crc = [uint32]0
    for ($i = 0; $i + 3 -lt $bytes.Length; $i += 4) { $crc = $crc -bxor [System.BitConverter]::ToUInt32($bytes, $i) }
    New-Item -ItemType Directory -Force $gsDir | Out-Null
    $gameIni = Join-Path $gsDir ('{0:X8}.ini' -f $crc)
    $slot1 = if ($MemCard -ne "") { "Slot1_Enable = true`r`nSlot1_Filename = $MemCard" } else { "Slot1_Enable = false" }
    # The same file turns the game's console output on for this run ([socom-port] trace lines:
    # every check reads them; a fresh profile has EE console logging off).
    [System.IO.File]::WriteAllText($gameIni, "[MemoryCards]`r`n$slot1`r`nSlot2_Enable = false`r`n`r`n[Logging]`r`nEnableEEConsole = true`r`nEnableIOPConsole = true`r`n")
    "memory cards for this run: $(if ($MemCard -ne '') { "slot 1 = $MemCard" } else { 'none' }) ($(Split-Path $gameIni -Leaf))"
} elseif ($MemCard -ne "") { "-MemCard needs the portable profile (SOCOM_PCSX2_PORTABLE=1): it never touches the user's own cards"; exit 1 }
if ($GameArgs -ne "") { $pargs += @('-gameargs', "`"$GameArgs`"") }
$pargs += @('-logfile', "`"$Log`"", '-elf', "`"$Elf`"", '--', "`"$disc`"")
$p = Start-Process $pcsx2 -PassThru -WindowStyle Minimized -ArgumentList $pargs

# Silent test runs: set this PCSX2's slider in the Windows volume mixer to 0 as soon as it opens
# its audio (PCSX2's own settings are untouched; set-appvolume.ps1 next to this script, skipped
# if absent). Windows remembers the mixer level per program, so the level is put back to 100%
# just before this run's PCSX2 is closed (below); socom-run.ps1 also sets its sessions to 100%.
$vol = Join-Path $PSScriptRoot 'set-appvolume.ps1'
if (Test-Path $vol) { Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$vol`"", '-ProcessId', $p.Id, '-Level', '0' | Out-Null }

# Watchdog: a hidden process that kills this PCSX2 at -Seconds + 30 even if this script is cut off.
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', "Start-Sleep -Seconds $($Seconds + 30); Stop-Process -Id $($p.Id) -Force -ErrorAction SilentlyContinue" | Out-Null

# Move the window as soon as it appears (poll every 50 ms for up to 15 s), then give focus back.
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 300 -and $h -eq [IntPtr]::Zero; $i++) {
    Start-Sleep -Milliseconds 50
    $p.Refresh(); $h = $p.MainWindowHandle
}
if ($h -ne [IntPtr]::Zero) {
    # Started minimized (so it never activates); restore it without activating (SW_SHOWNOACTIVATE = 4)
    # and move it onto the secondary monitor.
    $wasMin = [PcsxWin]::IsIconic($h)
    [PcsxWin]::ShowWindow($h, 4) | Out-Null
    [PcsxWin]::SetWindowPos($h, [IntPtr]::Zero, $area.X + 20, $area.Y + 20, 0, 0, $SWP_NOSIZE -bor $SWP_NOZORDER -bor $SWP_NOACTIVATE) | Out-Null
    # PCSX2 sometimes activates itself later than its first window (when the game window opens),
    # so watch for 8 s: whenever the foreground window belongs to this PCSX2, hand focus back.
    # A window the user switched to themselves is left alone.
    # When another PCSX2 is already running (several test runs at once) this one cannot open the
    # memory-card file and shows a "Memory Card Read Failed" dialog. The dialog is LEFT OPEN on
    # purpose (the user wants to see the error; -CloseCardDialog closes it as before): only the
    # focus is handed back, so it never keeps the keyboard.
    $start = Get-Date
    $closed = 0
    for ($i = 0; $i -lt 80; $i++) {
        Start-Sleep -Milliseconds 100
        if ($CloseCardDialog) { $closed += [PcsxWin]::CloseTitled([uint32]$p.Id, 'Memory Card Read Failed') }
        if ([PcsxWin]::OwnerPid([PcsxWin]::GetForegroundWindow()) -eq $p.Id) { [PcsxWin]::GiveBack($prev) }
    }
    if ($closed) { "closed $closed memory-card dialog(s) of this run (another emulator holds the card file)" }
    $r = New-Object PRECT; [PcsxWin]::GetWindowRect($h, [ref]$r) | Out-Null
    $fg = [PcsxWin]::GetForegroundWindow()
    "window at ($($r.Left),$($r.Top)); started minimized: $wasMin; focus kept: $([PcsxWin]::OwnerPid($fg) -ne $p.Id) (before '$([PcsxWin]::Title($prev))', now '$([PcsxWin]::Title($fg))')"
} else { "no window handle" }

function Save-Shot([IntPtr]$hwnd, [string]$file) {
    # A minimized window has no picture to copy (the screenshot came out blank or 160 x 28):
    # restore it first, without activating it (SW_SHOWNOACTIVATE = 4), and let it draw a frame.
    if ([PcsxWin]::IsIconic($hwnd)) { [PcsxWin]::ShowWindow($hwnd, 4) | Out-Null; Start-Sleep -Milliseconds 700 }
    $r = New-Object PRECT
    [PcsxWin]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top
    if ($w -le 0 -or $hh -le 0) { return "window has no size" }
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    $ok = [PcsxWin]::PrintWindow($hwnd, $hdc, 2)   # PW_RENDERFULLCONTENT
    $g.ReleaseHdc($hdc)
    # PrintWindow can return black for GPU-presented content; check a grid of pixels.
    $lit = $false
    for ($y = 40; $y -lt $hh -and -not $lit; $y += 40) { for ($x = 20; $x -lt $w; $x += 40) { $c = $bmp.GetPixel($x, $y); if ($c.R + $c.G + $c.B -gt 30) { $lit = $true; break } } }
    $how = "printwindow"
    if (-not $ok -or -not $lit) { $g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size); $how = "screen copy" }
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    "screenshot $file ($how)"
}

if ($ShotPrefix -eq "") { $ShotPrefix = [System.IO.Path]::ChangeExtension($Log, $null).TrimEnd('.') }
$times = if ($Shots -ne "") { $Shots.Split(",") | ForEach-Object { [int]$_ } } else { @($Seconds) }
if (-not $start) { $start = Get-Date }
# Wait-Run <t>: wait until <t> seconds into the run, in steps. Returns $true when the run should
# end now: PCSX2 exited, or -DonePattern has been seen -DoneCount times in the log and
# -DoneExtra seconds have passed since (so a run ends when its evidence is in the log instead of
# at a fixed time; -Seconds is then only the time limit).
$script:doneAt = $null
$script:doneMsg = $null
function Wait-Run([double]$until) {
    while ($true) {
        $p.Refresh()
        if ($p.HasExited) { return $true }
        $now = ((Get-Date) - $start).TotalSeconds
        if ($DonePattern -ne "") {
            if ($null -eq $script:doneAt) {
                $n = @(Select-String -Path $Log -Pattern $DonePattern -ErrorAction SilentlyContinue).Count
                # (kept in a variable: text written here would become part of the return value)
                if ($n -ge $DoneCount) { $script:doneAt = $now; $script:doneMsg = "done: '$DonePattern' x$n at $([int]$now) s" }
            }
            if ($null -ne $script:doneAt -and $now -ge $script:doneAt + $DoneExtra) { return $true }
        }
        if ($now -ge $until) { return $false }
        Start-Sleep -Milliseconds ([int]([Math]::Min(2.0, [Math]::Max(0.1, $until - $now)) * 1000))
    }
}
$ended = $false
foreach ($t in $times) {
    if (Wait-Run $t) { $ended = $true; if ($p.HasExited) { "PCSX2 exited before $t s" }; break }
    $file = if ($times.Count -gt 1) { "$ShotPrefix-$t.png" } else { "$ShotPrefix.png" }
    Save-Shot $p.MainWindowHandle $file
}
if (-not $ended) { Wait-Run $Seconds | Out-Null }
if ($script:doneMsg) { $script:doneMsg }
if (-not $p.HasExited) {
    # Put the mixer level back before closing, so the user's own PCSX2 is not left silent.
    if (Test-Path $vol) { & powershell -NoProfile -ExecutionPolicy Bypass -File $vol -ProcessId $p.Id -Level 1 -WaitSeconds 2 | Out-Null }
    Stop-Process -Id $p.Id -Force
}
Start-Sleep -Seconds 1
if ($gameIni -and (Test-Path $gameIni)) { Remove-Item $gameIni -ErrorAction SilentlyContinue }
Select-String -Path $Log -Pattern 'socom-port|STOP|xception|runtime error' -ErrorAction SilentlyContinue | Select-Object -Last 70 | ForEach-Object { $_.Line }
