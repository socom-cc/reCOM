# Stage 2: gamez/zMPEG (2026-11-25)

Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`, the function map
at HEAD 7614ca95). Checked by `socom-release-check-z2`, who did not write the tool. This was the
tool's first module that it had not been tuned on.

Scope: the 44 rows of `function-map.tsv` whose owner file is under `gamez/zMPEG` (13 exact,
21 deviating, 1 unsure, 5 new, 4 removed), plus the release function just before them
(0x34fe20). No release function between the rows is given to another module. Every row was
checked, the exact rows included: both sides were disassembled (objdump of the loaded images),
calls were named through the map, `$gp` operands were resolved to prototype symbols, and callers
were found by scanning both images for `jal`/`j` to the function. The check sheet
(`compare.py --sheet gamez/zMPEG`) was the starting point. Ghidra was not needed.

Evidence that settled rows, in the order it was used: the slot between two paired neighbours;
the call site in a paired caller (the same place in both builds); the function pointers passed
to `sceMpegAddCallback`; and what the body does. The prototype source (`src/gamez/zMPEG/`) gave
the roles of the globals.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x34fe70 | 0x333a90 `CMPEG::SetDisplayHeight(int)` | exact, position | confirmed | equal; `$gp` store to `_Display_Height` |
| 0x34fe80 | 0x333aa0 `CMPEG::SetMaxHeight(int)` | exact, position | confirmed | equal |
| 0x34fe90 | 0x333ab0 `CMPEG::Loop()` | exact | confirmed | equal; only address operands differ, and the `rsrcs` field offsets (+0x0 to +0x1c) agree |
| 0x34ffd0 | 0x333bf0 `CMPEG::Done()` | deviating, call-deviating | confirmed | the `BlockingPSSPlayback` test is gone: returns `testdonePss(p_mp)` |
| 0x34fff0 | 0x333c30 `CMPEG::End()` | deviating, call | confirmed | same callers (plus the new `RestartBackgroundMPEG` site); see What changed |
| 0x350110 | - | new | corrected to 0x333d50 `CMPEG::IdleTick()` | the same slot (between End and Tick); its caller `zVid_Swap` calls it at the same place (right after `sceGsSyncPath(0,0)`, before the T0 read); the same `fillBuff(p_mp, 0)` loop on T0 |
| 0x3501b0 | 0x333db0 `CMPEG::Tick(int)` | deviating, call-deviating | confirmed | the same callers; the blocking path now plays the whole movie (0x351680) and frees `p_mp` |
| 0x350230 | 0x333de0 `CMPEG::Run(const char*, bool, bool)` | deviating, position | confirmed | the same three callers; same open, Init and startPss sequence |
| 0x350320 | 0x333ec0 `CMPEG::Uninit()` | deviating, position, imm-only | confirmed | only the `_free` line numbers, each one lower (166–174 → 165–173) |
| 0x3503f0 | 0x333f90 `CMPEG::Init(void*, int)` | deviating, position | confirmed | `_memalign` line 64 → 63; the `initPssAudio` call is gone |
| 0x3508c0 | 0x334460 `sendToIOP2area(...)` | exact | confirmed | equal |
| 0x350c20 | - | new | confirmed | a helper split out of audioDecSendToIOP (see New and removed) |
| 0x350d00 | 0x3347c0 `audioDecSendToIOP(AudioDec*)` | deviating, position | confirmed | the same caller (tickPss), the same callees, and the state machine on `ad->state` |
| 0x350eb0 | 0x3349f0 `audioDecIsPreset` | exact | confirmed | equal |
| 0x350ed0 | 0x334a10 `audioDecEndPut` | exact | confirmed | equal |
| 0x350f60 | 0x334aa0 `audioDecBeginPut` | exact | confirmed | equal |
| 0x351020 | 0x334b80 `audioDecReset` | exact | confirmed | equal |
| 0x351070 | 0x3349a0 `audioDecStart` | exact, moved | confirmed | equal; it now comes after audioDecReset (source order changed) |
| 0x3510c0 | 0x334b60 `audioDecDelete` | exact, moved | confirmed | equal; moved like audioDecStart |
| 0x3510e0 | 0x334bd0 `audioDecCreate` | exact | confirmed | equal; its only caller is now startPss |
| 0x351150 | 0x334c40 `fillBuff(sceMpeg*, int)` | deviating, position | confirmed | the same read and demux body; the `sceMpegIsEnd` and `OKtoFillBuff` early exits are gone |
| 0x3511f0 | - | new | corrected to 0x334d10 `errorCallback(...)` | its address is the function pointer startPss passes to the third `sceMpegAddCallback` (`sceMpegCbError`, a1 = 0), as the prototype passes errorCallback; the same slot (between fillBuff and backgroundCallback) |
| 0x351220 | 0x334d20 `backgroundCallback(...)` | deviating, call-deviating | confirmed | the same registration in startPss; same blocking/non-blocking split |
| 0x3512f0 | 0x334d80 `nodataCallback(...)` | deviating, call-deviating | confirmed | the same body with `fillBuff(mp, 1)` inlined |
| 0x351480 | 0x334ec0 `audioCallback(...)` | deviating, call-deviating | confirmed | only the `doAudio` test is gone |
| 0x351560 | 0x334fb0 `videoCallback(...)` | deviating, call-deviating | confirmed | one added test: an empty ring counts as fully free |
| 0x351680 | - | new | corrected to 0x3350b0 `playPss(...)` | the same slot (between videoCallback and stopPss); the blocking whole-movie loop (`tickPss` until `sceMpegIsEnd`); the caller moved from Run to Tick and the signature gained `sceMpeg*` |
| 0x351920 | 0x3351b0 `stopPss(sceMpeg*)` | deviating, call | confirmed | the same calls; sets the new stop flag; `doAudio` test gone |
| 0x351970 | 0x335200 `testdonePss(sceMpeg*)` | deviating, call-deviating | confirmed | returns 1 when the stop flag is set, otherwise `sceMpegIsEnd != 0` |
| 0x3519b0 | 0x335220 `tickPss(sceMpeg*, playPssRsrcs*, unsigned)` | deviating, position | confirmed | the same picture, tag and audio sequence; adds `setjmp` error recovery and the read-ahead budget |
| 0x351c30 | 0x335440 `startPss(...)` | deviating, call | confirmed | the same `sceMpeg` setup and callback registrations in the same order |
| 0x351e50 | 0x335640 `uninitPssAudio()` | unsure, call-deviating, low-similarity | confirmed, deviating | the same callers (End, Uninit) and slot; now just a tail call to `audioDecDelete(&audioDec)` (the `doAudio` test is gone) |
| 0x351e60 | 0x3356b0 `loadImage(unsigned*)` | exact | confirmed | equal |
| 0x351e90 | 0x3356e0 `setLoadImageTagsYX(...)` | deviating, call, call-and-slot | confirmed | the same chain builder; the `_Display_Height` row clip is gone |
| 0x3520d0 | - | new | confirmed | a fill variant of setLoadImageTags (see New and removed) |
| 0x3520f0 | 0x335940 `setLoadImageTags(...)` | exact | confirmed | equal |
| 0x352110 | 0x335960 `strFileRead(void*, int)` | deviating, call | confirmed | `snd_DoExternCall('dstr', 5, …)` became a call to the new stream client 0x16f108 |
| 0x3521b0 | 0x335a10 `strFileClose()` | deviating, call-deviating | confirmed | extern call 4 → 0x16f0d0; both `CFileCD::m_streamingActive = 0` stores are gone |
| 0x352200 | 0x335a80 `strFileRewind()` | deviating, call | confirmed | extern call 2 → 0x16f0a0 |
| 0x352270 | 0x335b10 `strFileOpen(const char*)` | deviating, position | confirmed | `snd_StreamSafeCdSync(0)` → `sceCdDiskReady(0)`; extern calls 0/1 → 0x16f008/0x16f038; the `m_streamingActive = 1` store is gone |
| - | 0x333d50 `CMPEG::IdleTick()` | removed | corrected to 0x350110 | see 0x350110 |
| - | 0x334d10 `errorCallback(...)` | removed | corrected to 0x3511f0 | see 0x3511f0 |
| - | 0x3350b0 `playPss(...)` | removed | corrected to 0x351680 | see 0x351680 |
| - | 0x335670 `initPssAudio(playPssRsrcs*)` | removed | confirmed | inlined into startPss (audioDecCreate with `rsrcs` +0x18/+0x1c/+0x24, then `isStarted = 0`); Init no longer calls it |

Just outside the module:

| release | map | finding |
|---|---|---|
| 0x34fe20 | new, no owner | not zMPEG. It initializes a small object (word +0 = 1, bytes +12..+26, +15 = 1), sits right after `CZNetVoice::Init` and is reached only from 0x4863a0. That 12-byte stub (`lui a0,0x54; j 0x34fe20; addiu a0,0x5240`) sits in the static-initializer cluster at the place of the removed `__sinit_zNetVoice.cpp` (prototype 0x46ec50, just before `__sinit_reco.cpp`). It belongs to zNetVoice's check. |

## Settled pairs (tool input)

Rows whose class or counterpart differs from the map, or that the map left unsure. The rows
are in the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x350110 | 0x333d50 | caller zVid_Swap at the same place (after sceGsSyncPath); slot between End and Tick; same T0 read-ahead loop | socom-release-check-z2 | 2026-11-25 |
| 0x3511f0 | 0x334d10 | function pointer of the sceMpegCbError sceMpegAddCallback in startPss; slot between fillBuff and backgroundCallback | socom-release-check-z2 | 2026-11-25 |
| 0x351680 | 0x3350b0 | slot between videoCallback and stopPss; blocking loop of tickPss until sceMpegIsEnd; caller moved Run -> Tick | socom-release-check-z2 | 2026-11-25 |
| 0x351e50 | 0x335640 | callers End and Uninit; slot; audioDecDelete(&audioDec) | socom-release-check-z2 | 2026-11-25 |

All four are deviating. The other 40 rows stand as the map has them.

## What changed

### Layouts

No structure layout changes. `playPssRsrcs` (`rsrcs`, 48 bytes) keeps its field offsets
(mpegBuff +0x0 … audioBuffSize +0x1c, iopBuffSize +0x24). `AudioDec` is unchanged: all its
exact functions use the same offsets, and audioDecSendToIOP uses +0x0, +0x30 to +0x54.
`_zvid_public` keeps displayBuf/renderBuf at +0x30/+0x34 and the 1-byte `vidMode` at +0x51.
`_zsys_public` keeps isCdBoot at +0x1d and timerTicksPerSecond at +0x20. The 20-byte `infile` is
also unchanged.

The module's data did change:

| release | what | prototype |
|---|---|---|
| 0x48e6e0 … 0x48e6fc | zmpeg.cpp bss: BlockingPSSPlayback, internal_init, p_mp, the five *Alloc flags | 0x4767d8 … 0x4767f4, same order |
| 0x48e700 / 0x48e704 | isStarted / fileRead | 0x4767f8 / 0x4767fc |
| 0x48e708 | new: the read-ahead budget in T0 ticks (`(int)(width * height * 0.000151f)`, set by tickPss on the first picture, used by backgroundCallback) | - |
| 0x48e70c … 0x48e72c | OKtoFillBuff, gFrameCount, muxBuffFullness, path3tag, demuxBuff, demuxBuffSize, Past, Present, Future | 0x476800 … 0x476820 |
| 0x48e730 | new: stop flag (byte). Cleared by startPss; set by stopPss, by tickPss's error path and by pad button 0x40 in 0x351680; tested by testdonePss | - |
| 0x48e738 / 0x48e73c | dbp[2] | 0x476828 |
| 0x48e740 | new: T0 ticks per frame, `zSys.timerTicksPerSecond / 30` (set in 0x351680) | - |
| 0x48e744 | nonBlockReadReq (strfile.cpp) | 0x476830 |
| 0x48cff0 / 0x48cff4, 0x48cfe8 / 0x48cfec | new: IdleTick's T0 period and limit, 525/500 for NTSC and 1050/910 for DTV480P | the constants 525/480 |
| 0x48cff8 / 0x48cffc | _Max_Height / _Display_Height (480/448) | 0x475468 / 0x47546c |
| - | `doAudio` is gone: every test of it was dropped (audio always on) | 0x475464 |
| 0x564690 / 0x5646c0 / 0x564740 | rsrcs / audioDec / muxBuff[16384] | 0x52cb90 / 0x52cbc0 / 0x52cc40 |
| 0x568740 | new: a `jmp_buf` (setjmp in tickPss, longjmp from errorCallback) | (disp, 40 bytes, was here) |
| 0x568840 | new: 1024 bytes filled with 0x80000000, one black 16x16 PSMCT32 macroblock (written by startPss) | - |
| - | `disp` is gone: 0x351680 keeps its `sceGsDispEnv` on the stack | 0x530c40 |
| 0x568c40 | infile | 0x530c70 |
| 0x48e47c | new, outside zmpeg.cpp's bss: a byte set to 1 by Run (cleared when the open fails) and to 0 by End. No reader was found by a `$gp` or `lui`/offset scan | - |

### Functions

| function | change |
|---|---|
| Done | `BlockingPSSPlayback` test dropped |
| End | first calls `CVideo::MaxFrameRate(<frame rate at 0x48cf60, 30, also used by CCoreState::Init>)`; `BlockingPSSPlayback` test dropped (only `p_mp != NULL`); `_free` lines 257 → 287 and 166–174 → 165–173; clears 0x48e47c |
| IdleTick (0x350110) | T0 period/limit from `zVid.vidMode` (NTSC 525/500, DTV480P 1050/910; was 525/480). Quirk: for PAL neither is loaded and the loop uses the saved `s0`/`s1` uninitialized |
| Tick | blocking: `playPss(p_mp, strFileRead, &rsrcs)` (0x351680), `stopPss`, `_free(p_mp, line 230)`, `p_mp = 0`; non-blocking unchanged |
| Run | sets 0x48e47c; forces blocking when `strstr(name, "socom.pss")`; no `playPss` branch, always `_malloc(72, line 209)` + startPss; the `memset(p_mp, 0, 72)` is gone; ends with `MaxFrameRate(30)` |
| Uninit | `_free` lines −1 |
| Init | `_memalign` line 64 → 63; no `initPssAudio` call |
| audioDecSendToIOP | the state-2 area computation is now the out-of-line 0x350c20 (adds an "IOP position within 1024 bytes → send nothing" case); the state-1 areas go through the stack; frame 48 → 64 |
| fillBuff | `sceMpegIsEnd` and `!blocking && !OKtoFillBuff` exits dropped; only IdleTick calls it now |
| errorCallback (0x3511f0) | was `return 1`; now `longjmp(jmpbuf, 1)` (0x428b90), unwinding to tickPss |
| backgroundCallback | blocking: reads ahead (inlined fill, a single read when the buffer is empty) until T0 reaches T0-at-entry + budget (was absolute H-blank 480); non-blocking unchanged |
| nodataCallback | `fillBuff(mp, 1)` inlined; logic unchanged |
| audioCallback | `doAudio` test dropped |
| videoCallback | when `Present == Past` and `Present == Future` (empty ring) the room is `demuxBuffSize`, not 0 |
| playPss (0x351680) | rewritten: takes the `sceMpeg*` (allocation moved to Run); sets up its own display (640×448, FBW 10, and for DTV480P DISPLAY.DY + 18 instead of the prototype's DISPFB.DBY centring; moved from startPss); per frame alternates FBP 0/140, `tickPss`, IdleTick, waits for vsync (DTV480P: T0 ≥ ticks per frame), `sceGsPutDispEnv`, `CInput::Tick(1/30)`; pad button 0x40 sets the stop flag; loops until stop or `sceMpegIsEnd`; reset/delete/free moved to Tick/stopPss |
| stopPss | sets the stop flag; `doAudio` test dropped |
| testdonePss | stop flag or `sceMpegIsEnd` |
| tickPss | `setjmp(jmpbuf)` first: on a decoder error it sets the stop flag, resets audio, `sceMpegReset`/`sceMpegDelete`, returns 0; computes the read-ahead budget on the first picture; loads the second tags whenever `fbp != dbp[0]` (the `== dbp[1]` test is gone); `doAudio` test dropped |
| startPss | the blocking `sceGsResetGraph`/`sceGsResetPath` and display setup are gone (display moved to playPss); clears the stop flag; `initPssAudio` inlined; fills the black macroblock and loads it over the whole frame buffer (`0x3520d0(path3tag, block, 640, 2 * _Max_Height, 0)`, `loadImage`, `sceGsSyncPath`) before `sceMpegCreate`; the initial `fillBuff(mp, 1)` loop inlined |
| uninitPssAudio | `doAudio` test dropped (tail call) |
| setLoadImageTagsYX | no `_Display_Height` clip: every macroblock row is loaded; EOP on the last row of the last column |
| strFileRead / Close / Rewind / Open | `snd_DoExternCall('dstr', cmd, …)` replaced by a new EE stream client (0x16f008 init, 0x16f038 open, 0x16f0a0 seek, 0x16f0d0 close, 0x16f108 read; all go through 0x16f380 and keep their own open flag at 0x446e70); `snd_StreamSafeCdSync` → `sceCdDiskReady`; `CFileCD::m_streamingActive` no longer written here; read count shift `srl` → `sra` |

## New and removed

New in the module:

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x350c20 | from the IOP play position, computes the two IOP destination areas (ptr0, len0, ptr1, len1) for the next transfer in 1024-byte units; called only by audioDecSendToIOP | `iopGetArea(int*, int*, int*, int*, AudioDec*, int)`, a guess: the static helper of that name in the SDK's audiodec sample, whose argument order and arithmetic this matches; the prototype had it inline |
| 0x3520d0 | `setLoadImageTagsYX(tags, image, 0, width, height, dbp)`: step 0 repeats one macroblock over the whole area; called only by startPss to clear the frame buffer to black | a guess from the body: `setFillImageTags(unsigned*, void*, int, int, unsigned)`, the step-0 sibling of setLoadImageTags |

Not new, though the map has them as new: 0x350110 IdleTick, 0x3511f0 errorCallback and 0x351680
playPss. Their prototype names carry over. playPss's signature changed to
`(sceMpeg*, int (*)(void*, int), playPssRsrcs*)`, so its mangled name does not carry over
(`playPss__FP7sceMpegPFPvi_iP12playPssRsrcs` is a guess).

Removed: `initPssAudio`, whose work is inlined into startPss (the release has no `doAudio`
test left to keep it separate).

## Still unsure

None of the module's rows. Open points:

- The reader of the new byte 0x48e47c (set while a movie runs) was not found. It may be read
  through a pointer.
- The names of 0x350c20 and 0x3520d0 (guesses above).
- 0x34fe20 and 0x4863a0 belong to zNetVoice's check (the constructor of the object at 0x545240
  and the place of `__sinit_zNetVoice.cpp`). They are not settled here.
- `CFileCD::m_streamingActive`: zMPEG no longer writes it. Whether the release still has it
  is for the zFile/CFileCD check.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| exact | 13 | 13 | 0 |
| deviating | 21 | 21 | 0 |
| unsure | 1 | 1 (counterpart right; now deviating) | 0 |
| new | 5 | 2 | 3: 0x350110, 0x3511f0, 0x351680 have counterparts |
| removed | 4 | 1 | 3: the same three counterparts |

Owner attribution was right for every row, including the five owner-guess new rows. The
`moved` flags on audioDecStart/audioDecDelete are real (the source order changed). The one
neighbour with no owner (0x34fe20) is not zMPEG, and the tool did not claim it.

What misled it (the tool's own measures, recomputed for the three pairs):

- IdleTick ↔ 0x350110 (similarity 0.433, operations 0.667, sizes 92/148): enough for an
  unsure positional pair, but the shape 3-gram prefilter (Jaccard 0.038 < 0.15) dropped it
  before the similarity was computed. Through the caller it was also missed. `zVid_Swap`'s call
  list contains `sceGsSyncPath` three times and `sceGsSyncV` twice. The alignment matched
  IdleTick's neighbours to the first `SyncPath`/`SyncV` in the release, which are adjacent
  there, so IdleTick's gap had no release candidate. The real call follows the second
  `SyncPath`.
- errorCallback ↔ 0x3511f0 (8 bytes against 40): the size ratio 0.2 is under 0.25, so the
  callee resemblance was 0. Yet in startPss's reference list it is the only unpaired target
  between the same two `sceMpegAddCallback` anchors on both sides, and it fills a 1-to-1
  address slot.
- playPss ↔ 0x351680 (similarity 0.202, operations 0.333): the caller changed (Run → Tick) and
  most of the body was rewritten, so neither the call tree nor the position threshold (0.30)
  reached it. The only evidence is the 1-to-1 slot between videoCallback and stopPss and the
  role (the tickPss loop until `sceMpegIsEnd`).
- uninitPssAudio was rightly unsure by its numbers (a 3-instruction tail call against 10
  instructions); its callers settle it.

The sheet: it saved most of the work. For every row it gave the named reference lists, the
callers on both sides and the `__LINE__` strings. In the reference lists, "(unpaired)" on a
prototype reference next to "(new)" at the same place on the release side pointed straight at
two of the three wrong rows (errorCallback in startPss, initPssAudio in Init). What was missing
or misleading:

- No data operands are named. Every `$gp` and `lui`/low-half global had to be resolved by
  hand (BlockingPSSPlayback, doAudio, the new flags). Most of the deviating rows here are about
  globals.
- New and removed rows show no slot. "Between End (paired) and Tick (paired); removed in the
  same gap: IdleTick" would have made all three wrong rows a glance.
- The diffs are text diffs with address immediates unmasked (`lui a2,0x46` against `0x47` for
  the same string), so they misalign and stop after N blocks. The interesting functions
  (startPss, tickPss, Run) were cut off.
- `immediate deltas` only showed stack-frame changes here; it did not help.

Time per row (a scripted listing with names and `$gp` symbols plus a caller scan, both
read-only): exact about 20 seconds, in one batch; deviating 1–3 minutes (tickPss, startPss,
playPss and Run about 8 minutes each); unsure 3 minutes; new and removed about 5 minutes per
pair once the slots were looked at. About 75 minutes for the module, a quarter of it spent
resolving globals by hand.

What would make large modules cheaper:

- Pair a 1-to-1 gap: when exactly one unpaired function on each side lies between two paired
  neighbours (address slot), or between the same two anchors of a paired caller's ordered
  reference list, pair them as deviating, flagged `slot-only`, and skip the size ratio and gram
  prefilter. That alone settles all three wrong pairs here and the four of zArchive.
- In call-list alignment, do not let repeated anchors (the same SDK call several times) pick an
  occurrence that leaves a one-sided gap. Align on anchors that are unique in both lists first,
  or try the other occurrences when a gap stays one-sided. Also let a high operation similarity
  (≥ 0.6) override the 3-gram prefilter for functions under about 64 instructions.
- In the sheet, name data operands through the prototype symbols: release addresses mapped
  through the consistent operands of the paired functions. List the same-slot opposite for
  every new and removed row. Diff masked words rather than text, in full when the function is
  under about 200 instructions.
