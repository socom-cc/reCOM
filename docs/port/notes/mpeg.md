# boot-mpeg notes (2026-11-12, socom-port-mpeg)

Scratch for cinematics (PSS movies). Untracked. Changed files: `mine.txt` (= copy.txt for tree.sh).
Tools copied from boot-missionexit (paths -> boot-mpeg / tree-mpeg). New: `pss.py <file.pss>` (program
stream walk: packs, PES per stream, sequence header, SShd audio header).

## State / next step (latest first)
- DONE 18:31. Levels a, b, c work.
  rt1.log (mp-rt: death hook frame 200, pad_rt.txt): movie 1 PCM decoder IOP buffer 0xc8000, PCM start at
  picture 0 -> CROSS at read 400 -> 1.07 s fade -> "cinematic ends (skipped)" (50 pictures, 337920 PCM
  bytes sent) -> mission -> death 70.8 -> debrief 87.9 -> TRIANGLE -> menus -> PLAY GAME/START -> mission 2:
  movie 2 plays whole (130.97 -> 175.26 s, 1326 pictures, all 8467456 PCM bytes demuxed and sent to the
  IOP as 989snd played them) -> mission 2 to 237 s. No STOP/TLB/exception.
  default.log (mp-def, build_default.sh): main menu. Screens: build/port/screenshots/25-cinematics/.
- Next (not done): CGameMenu background MPEG (zui.cpp skip; CMPEG::Run/Loop/TickMPEG are ready for it);
  the last picture (1326 of 1327) is not output by ps2sdk's decoder; audio was verified by the transfer
  counts only (nobody listened).
- 18:25 r1.log (mp-f1): WORKS. PlayMPEG 57.2 s -> cinematic running -> "sequence 640x144, 33 ms" ->
  program end code 101.15 -> end of video after 1326 pictures (stream has 1327 picture headers; ps2sdk's
  decoder stops at 0x1B7 without the last one) -> cinematic ends (movie done) 101.68 -> mission frame 2,
  stable to 206 s (frame 6259), no STOP/TLB. 44.3 s for 1326 pictures = 29.97 fps (IdleTick pacing).
  Screens r1-68/80/95 movie frames (C-130, parachutes), r1-112/150/200 mission renders normally (motion
  data back from GS memory, textures fine). Running now: rt1 (mp-rt: skip CROSS at read 400, death hook
  frame 200, TRIANGLE 1250, PLAY GAME + START again 1350-1505, skip movie 2 at 1705) and mp-def built.
  PCM traces added (playpss: decoder IOP buffer, start, stop byte counts).
- 18:17 mp-f1 (fake pad START path, pad_m1.txt) links. Next: boot it, watch "MPEG:" traces at mission
  start (~62 s), then 90 s in mission.

## Survey (from the ELF)
Chain: m8 objectives anim UI_COMMAND 0x12 PlayMPEG 'run/movies/0122.pss' (61.9 s in the old logs, right
after CoreState Init) -> UIPlayMPEG 0x1d2c50 (alternate calls: SetMovie + theGame.Push(&m_cinematicSubState,
0), then the next call returns 1) -> CCinematicState (st_core.cpp):
- Init 0x17db20: CSnd::WaitForCDRead, FIFO end/disable, Clear black, MaxFrameRate(-1) (saved), display/
  render buffers to pages 0/70 (saved), zVid.doMpeg224 = 1, GIF_MODE IMT off, WriteGsMemory(gsTexAddr 9216,
  pBuffer_MotionRdr, mpegWorkspaceSize 0x1c0000) - the motion data is parked in GS memory and its buffer
  lent to the player -, SetMaxHeight/SetDisplayHeight(224), CMPEG::Init(buffer, size), Run(name, 1, 0).
- Tick 0x17d9d0: CInput::Tick; CROSS (m_state[PAD_CROSS] == KEY_FALLING) starts a 1.1 s fade (Fade
  alpha 1 -> 0 via bgcolor) and then stops; movie done or stopped -> CMPEG::End + theGame.Pop(0); else
  CMPEG::Tick(renderBuf) + zVid_Swap(1).
- UnInit 0x17d900: CMPEG::Uninit, FIFO end/disable, ReadGsMemory back, MaxFrameRate(saved), displayBuf 0,
  renderBuf = max(saved), doMpeg224 0, IMT on, free name, Fade(1).
CMPEG (zmpeg.cpp 0x333a90-0x334460): Init carves 5 areas from the buffer (decoder 2880*H+5992, picture
H/16*40960, PATH3 tags, 0x30000 video ring, 0xc000 PCM ring), Run (strFileOpen, startPss or blocking
playPss), Tick -> tickPss, IdleTick (zVid_Swap: fillBuff(0) until T0 (H-blanks since the swap) % 525 >= 480,
which also paces the movie to 30 fps), Done -> testdonePss, End, Uninit, Loop (front-end background loop).
playpss.cpp / audiodec.cpp / strfile.cpp (0x334460-0x335cc0): adapted Sony "ezmpeg" sample code compiled
as C++ in the game (mangled names) = authored. File via 989DSTRM.IRX ('dstr' extern calls through 989snd:
0 init, 1 open, 2 seek, 4 close, 5 read sectors) on CD boot. Video: demux -> videoCallback ring (uncached)
-> nodataCallback DMAs <= 4 KB to the IPU (D4 regs directly). Picture: sceMpegGetPicture (RGB32 16x16
macroblocks, column-major) -> setLoadImageTagsYX GIF chain -> loadImage (D2 chain) into the render buffer.
Audio: PSS private stream 1 = SPU2 PCM (SShd: type 1, 48000 Hz, 2 ch, 512 interleave) -> audioDec ring ->
SIF DMA into an IOP buffer from snd_InitMovieSound (989snd cmd 59) -> snd_StartMovieSound (62) once full;
snd_GetTransStatus (64) gives the play position. All 989snd client calls already exist (compat/snd989.c).
Provider: Sony libmpeg 0x154be8-0x15a4a0 (gcc2_compiled C: sceMpeg*, _ipu*, _decMB0, CSC) + libipu
(sceIpu* 0x15ab08-). Not in ps2sdk.
Disc movies (RUN/MOVIES): 0100, 0112, 0113, 0122 (m8 objectives: 640x144, 29.97 fps, 1327 pictures, MPEG-2,
44 s, PCM 48 kHz stereo), 0123, 0142, INTRO_2; COMMON/ SONY448 (640x448), ZIPPER02, DDATA, EXTRACT, KLAXON,
SRIDERS. Other movie caller: CGameMenu background MPEG (RestartBackgroundMPEG/LoadFromDesign/TickMPEG) -
not in scope (zui.cpp keeps its skip).
Stubs at the start (stubchk/fences/ctree): all of zMPEG (CMPEG 9 of 10, playpss 13, audiodec 9, strfile 7),
CCinematicState 5, CVideo::Fade (68 B), ReadGsMemory (340), WriteGsMemory (192), zvid_MpegReset (368);
UIPlayMPEG written but skipped the push.

## Provider route (port/compat)
pinned ps2sdk ships `libmpeg.a` (Eugene Plotnikov's IPU MPEG-1/2 decoder: MPEG_Initialize(dataCB, initCB),
MPEG_Picture, MPEG_Destroy; RGBA32 16x16 macroblocks row-major; the data callback is called in thread
context from _ipu_sync when the IPU FIFO is low and D4 QWC is 0, and must DMA to the IPU - the same contract
as the game's nodataCallback). No demuxer, no Sony API. `port/compat/libmpeg.c` = Sony-style sceMpeg* over it:
own program-stream demuxer (carry buffer for cut packets, stops after 0x1B9), GetPicture = MPEG_Picture +
column-major copy (InvalidDCache/SyncDCache), scratchpad 0-0x3c00 saved/restored, background callback once
per picture, EOF / no-data safety valve in the data callback (4000 empty requests -> end). Linked -lmpeg.
Also compat: sceGsSetDefStoreImage/sceGsExecStoreImage (VIF1 FDR + BUSDIR download), sceGsPutDispEnv,
sceIoctl, sceSifAllocIopHeap/FreeIopHeap (ps2sdk has sceSifSetDma/sceSifDmaStat itself).

## Written (ELF addresses)
zmpeg.cpp all 10; playpss.cpp all 13; audiodec.cpp all 9; strfile.cpp all 7; CCinematicState Init/Tick/
UnInit/SetMovie/dtor; CVideo::Fade 0x308ed0, ReadGsMemory 0x308ac0, WriteGsMemory 0x308a00 (now static);
zvid_MpegReset 0x308220; UIPlayMPEG push.

## ELF quirks kept
strFileRewind closes infile.fd on a failed CD seek; fillBuff(blocking) loops forever at EOF; audioCallback
strips the 4-byte sub-header before the room test; CMPEG::Init's _memalign line argument is 64; UnInit sets
displayBuf 0 and renderBuf to the larger saved page.

## Port deviations
- audiodec: the repeated SIF DMA sequence factored into a file-local SendDma.
- audioDecSendToIOP: an unknown state returns 0 (ELF continues with stale registers).
- muxBuff 64-aligned; CMPEG::Uninit/Loop static; CVideo Fade/Read/WriteGsMemory static.
- CVideo::MaxFrameRate stays the port's (no limiter in the port's zVid_Swap); IdleTick paces the movie.
