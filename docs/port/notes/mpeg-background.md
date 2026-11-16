# The menus' MPEG background (2026-11-15, socom-port-mpegbg)

The earlier port decision to leave the menus' background movies out (`mod-zui.md`, `mod-final.md`) is reversed:
`CGameMenu::LoadFromDesign` starts a design's movie as the ELF does, and the menus show it behind the 2D menu.
Scratch `build/port/boot-mpegbg/` (untracked: NOTES.md, mine.txt, the disc's design dumps under `disc/`).

## What the original does (ELF and disc)

- A design (`.rdr` in `run/ui/readerc.zar`) with `BACKGROUND (TYPE (MPEG) FILENAME (...))` has a movie for its
  background; no background image is loaded for it.
- `CGameMenu::LoadFromDesign` 0x382180 (at 0x382c44): `m_MPEGName` = the file, `m_has_mpeg_background` (+0x245) =
  1, `zSysFifoEnd`, `zSysFifoDisable`, `m_movieRunning` (+0x244) = `CMPEG::Run(name, 1, 0)`, `zSysFifoEnable(1)`;
  a movie that is not running then runs the design's `ONMPEGEND` anims at once.
- `CMenuState::Tick` 0x379240 calls `CGameMenu::TickMPEG` 0x381680 first in every frame: at the movie's end the
  `ONMPEGEND` anims run and `CMPEG::Loop` 0x333ab0 restarts it from the beginning (the movie loops until a menu
  switch); then one picture, FIFO ended and disabled around `CMPEG::Tick(zVid.renderBuf)`. The picture is loaded
  (PATH3 IMAGE chains, `tickPss` 0x335220) straight into the render buffer after the swap's clear, and the menu's
  backplane, world and foreplane are drawn over it. No texture is involved.
- `HaltBackgroundMPEG` 0x381790 (`CMenuState::OnPush` 0x379230: a state pushed over the menus; `UISetMission`
  0x1d5a60 around `theMission.PreOpen`) ends it; `RestartBackgroundMPEG` 0x381710 (`OnPop` 0x378e10, after the
  pre-open) runs it again from the start; `Clear` 0x3835a0 (every menu switch, the menu's dtor) ends it. No other
  code reads +0x244 / +0x245; a pop-up does not pause it.
- No `CMPEG::Init` in the menus: `Run` 0x333de0 allocates the work areas itself for 480 lines (decoder 1,388,392,
  picture 1,228,800, PATH3 tags 230,912, video ring 196,608, PCM ring 49,152 = 3,093,864 B, plus the 24 KB IOP PCM
  buffer) and `End` frees them. It shares `CMPEG`, the stream reader and the IPU with the mission's cinematic
  state, which is only pushed from a mission (the menus are gone then). While a movie runs, `CMPEG::IdleTick` in
  `zVid_Swap` reads ahead until H-blank 480: the menus run at 30 fps.
- The disc (demo, May 2002): reachable designs with a movie are `dlgIntroCinematic` (`common/sony448.pss`, 4 s, then
  `switch_menu dlgIntroZipperCinematic`), `dlgIntroZipperCinematic` (`common/Zipper02.pss`, 4 s, then `dlgMenu`) and
  `dlgAlaskaCinematic` (`0100.pss`, 44.7 s, after NEW GAME; START / CROSS skip to the briefing). The main menu
  `dlgMenu` has an image (`splashBack.tif`). The retail game's looping backgrounds `common/menuloop.pss`
  (`dlgPBMenu`, `dlgMenuMp`) and `common/radar.pss` (`dlgMISSIONSELECTION`, `dlg_equipment_main`, the area / mission
  screens) are not on the demo disc: on those menus `strFileOpen` fails and `ONMPEGEND` runs at once, as in the
  original with this disc. `dlgAttractCinematic` (`Intro_2.pss`) is named by no design or code.

## Written

- `src/gamez/zUI/zui.cpp`: `LoadFromDesign`'s movie start (0x382c44-0x382cb4), with a `UI: background movie` trace.
  Everything else of the path (`TickMPEG`, `Halt` / `RestartBackgroundMPEG`, `Clear`, `CMenuState`'s callers,
  all of `CMPEG`, playpss / audiodec / strfile) was already written.
- `port/compat/libmpeg.c` (the SDK side):
  - The fix that makes 640x448 movies play: the pinned ps2sdk 2.0.0 `libmpeg.a` converts a picture to RGBA32 (CSC)
    in chunks of 1023 macroblocks, and its DMAC channel 3 handler starts the chunks after the first with the D3 /
    D4 quadword counts swapped. A picture of more than 1023 macroblocks (640x448 = 1120) left output in the IPU
    FIFO and the IPU busy; the next picture hung in the decoder's IPU wait (traced: IPU_CTRL 0x83200483, OFC 8, D3
    stopped after 48 qw). The mission movies (640x144, 640x368: 360 / 920 macroblocks) never reach a second chunk.
    ps2sdk fixed the handler upstream on 2026-11-01 (commit 10c8b450). Here a second channel 3 handler, registered
    after ps2sdk's so it runs first, restarts D3 for the rest of the picture when it stops at the short count
    (ps2sdk's handler is skipped for that interrupt) and stops the overlong D4 input at the picture's end; ps2sdk's
    handler then ends the conversion. Up to 2046 macroblocks (two chunks); the disc's largest is 1120.
  - The decoder's output picture now goes into the caller's work area (`sceMpegCreate`'s, which Sony's decoder
    works in and ps2sdk's does not use) when it is large enough, instead of a separate allocation: 1,146,880 B
    less while a 640x448 movie plays.
- Test hook `port/test-hooks/mpegbg/` (README row): the boot movies, `dlgPBMenu` / `dlgMISSIONSELECTION` with
  stand-in movies for the missing retail files (a wrapped `strFileOpen`), a switch to an image menu and back,
  NEW GAME and the Alaska cinematic skipped; `CMPEG` Run / Loop / End, pictures, frame time and heap traced;
  `-DSOCOM_HOOK_DIAG=n` adds the IPU / DMAC watchdog that found the hang.
- Pad scripts shifted for the new boot timing (below): `common/pad_fe.txt`, `common/pad_start.txt`, `win/pad_a1.txt`.

## Results

- Hook runs mb10 / mb11 (`port/test-hooks/mpegbg/build.sh`, 80-90 s): the Sony title and the Zipper logo play
  whole at boot (120 pictures each, PCM sent to the IOP), `dlgMenu` (image) follows; `dlgPBMenu` with the stand-in
  movie loops twice behind its unchanged menu (screens 29 s / 31 s: the Zipper logo, then its dark part), back to
  `dlgMenu`, `dlgPBMenu` again (the movie starts from its beginning), `dlgMISSIONSELECTION` loops its stand-in,
  `dlgMenu`, NEW GAME: `dlgAlaskaCinematic` plays `0100.pss` (640x368, centred) until CROSS at picture 317, then
  the briefing. No STOP. Screens: `build/port/screenshots/60-mpegbg/` (untracked).
- Frame time in the menus: 33.3 ms (30 fps) while a movie plays, 16.7 ms on `dlgMenu` without one.
- Heap (state hook, gate round trip): main menu (`dlgMenu`, first) in use 18,158,652 B, largest free block
  8,863,744 B, the same as HEAD (the boot movies are freed before it). While a 640x448 movie plays: in use
  22.56 MB at boot (23.70 MB before the work-area change); `dlgAlaskaCinematic` after a return 22,344,812 B,
  largest free block 2.73-2.85 MB, break at most 0x1d45000 (heap end 0x1fdf000).
- Gate on HEAD 048048fa + these files (`gate.ps1`, all four): default (main menu after the two intro movies),
  frontend (13 menu switches, the options screens), win (debrief at 216.6 s, objectives 3/7) and roundtrip (four
  missions, the Alaska cinematic played whole before each: in use at the returns 18,657,260 B, flat; largest free
  block 3,956,736 B, 2,576,384 B at one return where the menus' archive buffer went above the break, brk
  0x1e93000) all PASS. HEAD alone gave the same figures (one return of four with the buffer above the break), so
  the movie's buffers, allocated after the menus' archive and freed before the mission load, do not change where
  that buffer goes.

## Consequences for test scripts

- The two intro movies have no skip (as in the ELF): the main menu now comes about 8 s later, at fake-pad read
  ~124 instead of ~0 (reads come every other frame, and the menus run at 30 fps while a movie plays).
- NEW GAME now plays `dlgAlaskaCinematic` (44.7 s) before the briefing; CROSS or START skips it.
- `pad_fe.txt` is shifted by +125 reads; `pad_start.txt` and `win/pad_a1.txt` press CROSS at 185 (PLAY GAME), CROSS
  at 215 (skip the cinematic), and everything after 130 moves by +165. The other per-feature pad files that open
  with `60:CROSS,130:DOWN,...` are not shifted; the same rule applies to them. The state hook (round trip) is
  driven by the dialog name and lets the Alaska cinematic play to its end (`ONMPEGEND` -> briefing).

## Pacing and the frame limiter (for whoever writes `zVid_Swap`'s limiter)

The menu movie has no clock of its own: one picture is decoded and loaded per menu frame (`TickMPEG`), and the
frame is held by `CMPEG::IdleTick` in `zVid_Swap`, which reads ahead until T0 (H-blanks since the last swap) reaches
line 480 of 525, so the swap's V-sync wait lands on the second field: 30 frames, 30 pictures a second (the movies
are 29.97 / 30 fps), and the IOP plays the PCM in real time beside it. The port's `zVid_Swap` has no limiter yet
(`mpeg.md`). The ELF's limiter waits whole fields while `procTime + 1/60 < 1 / CVideo::m_maxFrameRate`; in the menus
`procTime` is already about 480 lines (30.5 ms) after `IdleTick`, so at the default 30 it adds no field. Re-check
when the limiter lands: a menu with a movie must stay at 33 ms a frame (an extra field gives 20 pictures a second:
the picture falls behind the PCM, the PCM ring fills and the demuxer stalls on audio), and a menu without one goes
from 60 to the limit. The cinematic state sets `MaxFrameRate(-1)` and restores it; the menus set nothing.

## ELF behaviour kept

- At a movie's end `TickMPEG` runs `ONMPEGEND` and loops the movie even when the anim switches the menu: the
  cinematic menus restart their movie for one picture before the switch ends it (traced: `CMPEG::Loop`, then
  `CMPEG::End after 1 pictures`; the Alaska cinematic's `goto_menu` fades first, so its movie restarts for 15
  pictures).
- `RestartBackgroundMPEG` starts the movie from its beginning (`End` freed everything); `UISetMission` halts and
  restarts it around the mission pre-open.
- The movie decides the menus' frame rate (30 fps through `CMPEG::IdleTick`).

## Port deviations

- `port/compat/libmpeg.c` only: the CSC second-chunk fix and the output picture in the work area (above). ps2sdk's
  decoder still allocates its own reference frames (about 1.3 MB for 640x448) that Sony's decoder keeps in the
  work area, so the port uses that much more while a movie plays.
- The last picture of a stream is not output by ps2sdk's decoder (120 of 121 for the 4 s movies), as `mpeg.md`
  notes for the mission movies.
