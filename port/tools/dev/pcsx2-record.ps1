param(
    [Parameter(Mandatory = $true)][string]$Elf,       # Windows path to the ELF to boot (copy it out of WSL first; run.ps1 does)
    [Parameter(Mandatory = $true)][string]$Log,       # PCSX2 log file
    [int]$Seconds = 40,                               # kill PCSX2 after this many seconds
    [string]$Shots = "",                              # screenshot times in seconds, e.g. "20,35"; empty = one at -Seconds
    [string]$ShotPrefix = "",                         # screenshot path without extension; empty = next to the log
    [Parameter(Mandatory = $true)][string]$Video,     # output .mp4
    [int]$From = 0,                                   # record from this second ...
    [int]$To = 0,                                     # ... to this one (0 = -Seconds)
    [int]$Fps = 10,                                   # target frame rate (PrintWindow frames; window only, no audio)
    [string]$StartPattern = "",                       # regex: start recording when a log line matches (after -From); the clip
                                                      # should open on the feature, not on loading or the walk-up
    [int]$Length = 0                                  # with -StartPattern: record this many seconds (0 = until -To)
)
# Recording variant of pcsx2-boot.ps1 ($env:SOCOM_PCSX2, $env:SOCOM_DISC_IMAGE; ffmpeg on PATH): same boot, plus
# PrintWindow frames of the PCSX2 window only (never the rest of the screen) between -From and -To, encoded to
# -Video with ffmpeg. No audio. Frames carry their real capture times, so playback speed is true.
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
# and older than 5 minutes.
Get-CimInstance Win32_Process -Filter "Name = 'pcsx2-qt.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*-batch*' -and ((Get-Date) - $_.CreationDate).TotalMinutes -gt 5 } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "closed stale test run $($_.ProcessId)" }

$prev = [PcsxWin]::GetForegroundWindow()
if (Test-Path $Log) { Remove-Item $Log }
$p = Start-Process $pcsx2 -PassThru -WindowStyle Minimized -ArgumentList '-nogui', '-batch', '-fastboot', '-earlyconsolelog', '-logfile', "`"$Log`"", '-elf', "`"$Elf`"", '--', "`"$disc`""

# Quiet test runs: set this PCSX2's slider in the Windows volume mixer to 15% as soon as it opens
# its audio (PCSX2's own settings are untouched; set-appvolume.ps1 next to this script, skipped
# if absent). socom-run.ps1 sets its sessions back to 100%.
$vol = Join-Path $PSScriptRoot 'set-appvolume.ps1'
if (Test-Path $vol) { Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$vol`"", '-ProcessId', $p.Id, '-Level', '0.15' | Out-Null }

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
    Start-Sleep -Milliseconds 500
    if ([PcsxWin]::GetForegroundWindow() -ne $prev) { [PcsxWin]::GiveBack($prev) }
    $r = New-Object PRECT; [PcsxWin]::GetWindowRect($h, [ref]$r) | Out-Null
    $fg = [PcsxWin]::GetForegroundWindow()
    "window at ($($r.Left),$($r.Top)); started minimized: $wasMin; focus kept: $($fg -eq $prev) (before '$([PcsxWin]::Title($prev))', now '$([PcsxWin]::Title($fg))')"
} else { "no window handle" }

function Save-Shot([IntPtr]$hwnd, [string]$file) {
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

function Save-Frame([IntPtr]$hwnd, [string]$file) {
    $r = New-Object PRECT
    [PcsxWin]::GetWindowRect($hwnd, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top
    if ($w -le 0 -or $hh -le 0) { return $false }
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    $ok = [PcsxWin]::PrintWindow($hwnd, $hdc, 2)
    $g.ReleaseHdc($hdc)
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $g.Dispose(); $bmp.Dispose()
    return $ok
}
if ($To -le 0) { $To = $Seconds }
$frames = Join-Path ([System.IO.Path]::GetDirectoryName($Video)) ([System.IO.Path]::GetFileNameWithoutExtension($Video) + "-frames")
if (Test-Path $frames) { Remove-Item $frames -Recurse -Force }
New-Item -ItemType Directory -Path $frames | Out-Null
$start = Get-Date
$wait = $From - ((Get-Date) - $start).TotalSeconds
if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]($wait * 1000)) }
if ($StartPattern -ne "") {
    # Follow the live log (shared read) until a line matches; give up at -To.
    $pos = 0L; $hit = $false
    while (-not $hit -and ((Get-Date) - $start).TotalSeconds -lt $To) {
        $p.Refresh(); if ($p.HasExited) { break }
        if (Test-Path $Log) {
            $fs = [System.IO.File]::Open($Log, 'Open', 'Read', 'ReadWrite')
            try {
                if ($fs.Length -gt $pos) {
                    $fs.Position = $pos; $buf = New-Object byte[] ($fs.Length - $pos)
                    $got = $fs.Read($buf, 0, $buf.Length); $pos += $got
                    $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $got)
                    $m = [regex]::Match($text, "(?m)^.*(?:$StartPattern).*$")
                    if ($m.Success) { $hit = $true; "start pattern matched at $([int]((Get-Date) - $start).TotalSeconds) s: $($m.Value.Trim())" }
                }
            } finally { $fs.Dispose() }
        }
        if (-not $hit) { Start-Sleep -Milliseconds 100 }
    }
    if (-not $hit) { "start pattern never matched; nothing recorded" }
    elseif ($Length -gt 0) { $To = [Math]::Min($To, [int]((Get-Date) - $start).TotalSeconds + $Length) }
    if (-not $hit) { $To = 0 }
}
$list = New-Object System.Collections.Generic.List[string]
$n = 0; $last = $null; $t0 = Get-Date; $step = 1000.0 / $Fps
while (((Get-Date) - $start).TotalSeconds -lt $To) {
    $p.Refresh(); if ($p.HasExited) { "PCSX2 exited during the recording"; break }
    $tick = Get-Date
    $file = Join-Path $frames ("f{0:d5}.jpg" -f $n)
    if (Save-Frame $p.MainWindowHandle $file) {
        if ($last) { $list.Add("duration {0:f3}" -f ($tick - $lastTick).TotalSeconds) }
        $list.Add("file '$($file.Replace('\','/'))'"); $last = $file; $lastTick = $tick; $n++
    }
    $spent = ((Get-Date) - $tick).TotalMilliseconds
    if ($spent -lt $step) { Start-Sleep -Milliseconds ([int]($step - $spent)) }
}
if ($last) { $list.Add("duration {0:f3}" -f ($step / 1000)); $list.Add("file '$($last.Replace('\','/'))'") }
"recorded $n frames in $([int]((Get-Date) - $t0).TotalSeconds) s"
if ($StartPattern -ne "") { $Seconds = [int]((Get-Date) - $start).TotalSeconds }
$wait = $Seconds - ((Get-Date) - $start).TotalSeconds
if ($wait -gt 0 -and -not $p.HasExited) { Start-Sleep -Milliseconds ([int]($wait * 1000)) }
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep -Seconds 1
$listFile = Join-Path $frames "list.txt"
[System.IO.File]::WriteAllLines($listFile, $list)
if (Test-Path $Video) { Remove-Item $Video }
if ($n -gt 0 -and -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { "ffmpeg is not on PATH; frames kept in $frames"; $n = -1 }
if ($n -gt 0) { & ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $listFile -vf "fps=$Fps,scale=trunc(iw/2)*2:trunc(ih/2)*2" -c:v libx264 -pix_fmt yuv420p -crf 26 -preset veryfast $Video }
if ($n -lt 0) { } elseif ($n -eq 0) { "no frames; no video" } elseif (Test-Path $Video) { "video $Video ($([int]((Get-Item $Video).Length / 1KB)) KB)"; Remove-Item $frames -Recurse -Force } else { "ffmpeg failed; frames kept in $frames" }
Select-String -Path $Log -Pattern 'STOP|xception|runtime error' -ErrorAction SilentlyContinue | Select-Object -Last 5 | ForEach-Object { $_.Line }
