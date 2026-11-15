param(
    [string]$Build = "gate",        # shared WSL build dir under ~/.cache/socom (kept between runs: incremental)
    [int]$Missions = 4,             # missions (= returns to the menus) in the round trip
    [switch]$SkipBuild,             # boot the ELFs of the last gate run again
    [switch]$BuildOnly,             # build the four ELFs and stop (boot them later with -SkipBuild)
    [string[]]$Only = @()           # run only these checks: default, frontend, win, roundtrip
)
# gate.ps1: the full behaviour check of one tree, in one command. It builds the isolated tree
# (tree.sh --fresh: HEAD plus the scratch folder's mine.txt / shared.txt; an empty mine.txt = HEAD
# alone) and boots four test builds side by side:
#   default    no hook, no fake pad: reaches the main menu
#   frontend   fake pad through the options screens (port/test-hooks/common/pad_fe.txt)
#   win        the scripted m8 playthrough (port/test-hooks/win): debrief with objectives 3/7
#   roundtrip  menus -> m8 -> menus, -Missions times (port/test-hooks/state, malloc traced):
#              in-use equal at every return from the second on
# All four fail on a STOP, a TLB miss or an assert in the log. The four ELFs are built one after
# the other in ONE build dir (only the fake pad file and the link differ), copied to the scratch
# folder as gate-<check>.elf, and booted together through pcsx2-boot.ps1, so the wall-clock time is
# the longest run (the round trip), not the sum. Each run ends when its evidence is in the log
# (pcsx2-boot.ps1 -DonePattern), not at a fixed time. Prints a table and exits 0 only if all passed.
# Needs SOCOM_PCSX2 and SOCOM_DISC_IMAGE (user-local) as pcsx2-boot.ps1 does.
. (Join-Path $PSScriptRoot '_dev.ps1')
$ErrorActionPreference = 'Continue'
$dir = Get-SocomScratch
try { Get-SocomPcsx2 | Out-Null; Get-SocomDisc | Out-Null } catch { "$($_.Exception.Message)"; exit 2 }
$wsl = Join-Path $PSScriptRoot 'wsl.ps1'
$boot = Join-Path $PSScriptRoot 'pcsx2-boot.ps1'
$w = Get-SocomWslArgs

# Seconds is a time limit, generous because several emulators share the machine (a loaded host
# runs them slower than real time); each run ends as soon as Done has been seen Count times.
$checks = @(
    @{ Name = 'default';   Seconds = 150; Done = 'MENU: CMenuState::Init done'; Count = 1; Extra = 8
       Build = { & $wsl fake.sh $Build '-' } },
    @{ Name = 'frontend';  Seconds = 300; Done = 'UI: SwitchMenu'; Count = 10; Extra = 15
       Build = { & $wsl fake.sh $Build 'port/test-hooks/common/pad_fe.txt' } },
    @{ Name = 'win';       Seconds = 520; Done = 'EXIT: debrief open'; Count = 1; Extra = 8
       Build = { & $wsl port/test-hooks/win/build.sh $Build 'port/test-hooks/win/pad_a1.txt' '-DSOCOM_HOOK_WIN' } },
    @{ Name = 'roundtrip'; Seconds = (120 + 160 * $Missions); Done = 'heap return \d+ to the menus: largest'; Count = $Missions; Extra = 5
       Build = { & $wsl port/test-hooks/state/build.sh $Build 'port/test-hooks/state/pad_idle.txt' '-DSOCOM_HOOK_MALLOC' "-DSOCOM_HOOK_MISSIONS=$Missions" } }
)
if ($Only.Count -gt 0) { $checks = @($checks | Where-Object { $Only -contains $_.Name }) }
$t0 = Get-Date

$headFile = Join-Path $dir 'gate-head.txt'
if (-not $SkipBuild) {
    # what the ELFs are built from: HEAD at build time (the report names this, not a later HEAD)
    Set-Content -Encoding ascii $headFile ((& git -C $SocomRepo log --oneline -1) -replace '^(.{70}).*$', '$1')
    $out = & $wsl tree.sh --fresh 2>&1
    $out | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) { "gate: tree.sh failed"; exit 2 }
    foreach ($c in $checks) {
        $elf = Join-Path $dir "gate-$($c.Name).elf"
        if (Test-Path $elf) { Remove-Item $elf }
        $out = & $c.Build 2>&1
        $welf = ConvertTo-SocomWslPath $elf
        & wsl.exe @w -e bash -c "cp `"`$HOME/.cache/socom/$Build/socom_port.elf`" '$welf'" 2>$null
        if (-not (Test-Path $elf)) { "gate: build of '$($c.Name)' failed:"; $out | Select-Object -Last 15; exit 2 }
        "built $($c.Name)  ($([int]((Get-Date) - $t0).TotalSeconds) s)"
    }
}

if ($BuildOnly) { "gate: built in $([int]((Get-Date) - $t0).TotalSeconds) s; boot with -SkipBuild"; exit 0 }
$procs = @()
foreach ($c in $checks) {
    $elf = Join-Path $dir "gate-$($c.Name).elf"
    if (-not (Test-Path $elf)) { "gate: no $elf (build first)"; exit 2 }
    $log = Join-Path $dir "gate-$($c.Name).log"
    $rep = Join-Path $dir "gate-$($c.Name).run.txt"
    $cmd = "& '$boot' -Elf '$elf' -Log '$log' -Seconds $($c.Seconds) -DonePattern '$($c.Done)' -DoneCount $($c.Count) -DoneExtra $($c.Extra) > '$rep' 2>&1"
    $procs += Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd
    Start-Sleep -Seconds 3
}
$longest = ($checks | ForEach-Object { $_.Seconds } | Measure-Object -Maximum).Maximum
$deadline = (Get-Date).AddSeconds($longest + 120)
while ((Get-Date) -lt $deadline -and @($procs | Where-Object { -not $_.HasExited }).Count -gt 0) { Start-Sleep -Seconds 5 }

function Test-GateLog([string]$name, [string]$log) {
    if (-not (Test-Path $log)) { return @{ Ok = $false; Note = 'no log' } }
    $bad = @(Select-String -Path $log -Pattern 'STOP:|TLB miss|ssert' -CaseSensitive)
    if ($bad.Count -gt 0) { return @{ Ok = $false; Note = "$($bad.Count) STOP / TLB / assert line(s): $($bad[0].Line.Trim().Substring(0, [Math]::Min(90, $bad[0].Line.Trim().Length)))" } }
    switch ($name) {
        'default' {
            $m = Select-String -Path $log -Pattern 'MENU: CMenuState::Init done' | Select-Object -First 1
            if ($m -and $m.Line -match '^\[\s*([\d.]+)\]') { return @{ Ok = $true; Note = "main menu at $($Matches[1]) s" } }
            return @{ Ok = $false; Note = 'the main menu was not reached' }
        }
        'frontend' {
            $n = @(Select-String -Path $log -Pattern 'UI: SwitchMenu').Count
            if ($n -ge 4) { return @{ Ok = $true; Note = "$n menu switches" } }
            return @{ Ok = $false; Note = "only $n menu switches" }
        }
        'win' {
            $m = Select-String -Path $log -Pattern 'EXIT: debrief open \(objectives (\d+)/(\d+)' | Select-Object -First 1
            if (-not $m) { return @{ Ok = $false; Note = 'no debrief' } }
            $o = "$($m.Matches[0].Groups[1].Value)/$($m.Matches[0].Groups[2].Value)"
            $t = if ($m.Line -match '^\[\s*([\d.]+)\]') { $Matches[1] } else { '?' }
            return @{ Ok = ($o -eq '3/7'); Note = "debrief at $t s, objectives $o" }
        }
        'roundtrip' {
            $use = @(Select-String -Path $log -Pattern 'heap return (\d+) to the menus: arena \d+ in use (\d+)' | ForEach-Object { [int64]$_.Matches[0].Groups[2].Value })
            $big = @(Select-String -Path $log -Pattern 'heap return \d+ to the menus: largest free block (\d+)' | ForEach-Object { [int64]$_.Matches[0].Groups[1].Value })
            if ($use.Count -lt $Missions) { return @{ Ok = $false; Note = "$($use.Count) of $Missions returns" } }
            $flat = @($use | Select-Object -Skip 1 | Sort-Object -Unique).Count -le 1
            $onTop = @($big | Where-Object { $_ -lt 3000000 }).Count
            return @{ Ok = $flat; Note = "$($use.Count) returns, in use $($use[-1]) B $(if ($flat) { 'flat' } else { 'NOT flat: ' + ($use -join ' ') }); menu buffer above the break at $onTop return(s)" }
        }
    }
}

$fail = 0
""
"gate: built from $(if (Test-Path $headFile) { Get-Content $headFile -TotalCount 1 } else { '?' })$(if (Test-Path (Join-Path $dir 'mine.txt')) { $m = @(Get-Content (Join-Path $dir 'mine.txt') | Where-Object { $_ -and $_ -notmatch '^\s*#' }); if ($m.Count) { " + $($m.Count) file(s) of mine.txt" } })"
foreach ($c in $checks) {
    $log = Join-Path $dir "gate-$($c.Name).log"
    $rep = Join-Path $dir "gate-$($c.Name).run.txt"
    $r = Test-GateLog $c.Name $log
    $focus = if ((Test-Path $rep) -and (Select-String -Path $rep -Pattern 'focus kept: False' -Quiet)) { ' [focus NOT kept]' } else { '' }
    if (-not $r.Ok) { $fail++ }
    "{0,-5} {1,-10} {2}{3}" -f $(if ($r.Ok) { 'PASS' } else { 'FAIL' }), $c.Name, $r.Note, $focus
}
"gate: $(if ($fail) { "$fail FAILED" } else { 'all passed' }) in $([int]((Get-Date) - $t0).TotalSeconds) s (logs: $dir\gate-*.log)"
exit $(if ($fail) { 1 } else { 0 })
