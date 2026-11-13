# boot-sound notes (2026-11-07)

Scratch for the sound worker (functional port). Nothing here is tracked. Changed files: `mine.txt`.

## Tools here
- `dx.ps1 <addr> [end|+len]` (objdump of support/socom.elf, zero words shown), `sym.py`, `xref.py`,
  `gpref.py 0xADDR` ($gp / lui+lo references to data), `status.py`, `dw.py`, `rdr.py`, `iso.py`.
- `tree.sh` + `build.sh <name> [pad-script [CFLAGS]]`: isolated tree (HEAD + mine.txt) built in
  ~/.cache/socom/sound-<name>. `build.sh probe "$(cat pad_w.txt)" -DSOCOM_PORT_SOUND_PROBE` = test build.
- Disc files read into the session scratchpad only (readerc.zar sounds.rdr, bnkstore.zar, czanim.zar).
- asm dumps: asm_989snd.txt (EE library), asm_zsound.txt (zSound), asm_zanim*.txt, asm_sealstep.txt.

## Sound stack (from the ELF)
- IOP: RebootIOP (0x2f4e90) loads RUN\IRX\LIBSD.IRX, SDRDRV.IRX, SOUND\989SND.IRX (args
  "stream_priority=18"), SOUND\989DSTRM.IRX from the disc after IOPRP250.IMG. They already loaded
  in the port; 989snd v2.9.0 (snd989 1.08) registers RPC 0x123456 (commands) and 0x123457 (loader).
- EE client 989snd.c (0x2ea400-0x2ebd20, provider): batch buffers 2x4096 (count, then u16 id,
  u16 size, data padded to 4) sent with rpc 77, answers count+2 words (-1 markers, results);
  single commands use the command id as rpc number (answer {-1, result, -1}); bank load rpc 2
  (flags + name) / rpc 3 (sector, offset), answer = bank handle. Callbacks run in
  snd_FlushSoundCommands. Command ids: 0 start (data = &gStats), 1 stop, 6 unload bank,
  8 resolve xrefs, 9/10 set/get master vol, 11/12 playback mode, 14 reverb type, 16 auto reverb,
  17/18 play vol pan pm pb (cb / no cb), 19 pause, 20 continue, 21 stop, 25 still playing,
  27 vol/pan, 30 pitch, 33 params, 34 auto vol, 42 init VAG streaming, 44 play VAG stream by loc,
  52 stop streams, 53 close streaming, 54 CD idle, 56 CD read via IOP (after streaming init all
  CFileCD reads go through it), 59-62/64 movie sound, 76 extern call.
- Game: CSnd (sounds.rdr SETS -> mission -> bank sets), banks <name>.BNK in BNKSTORE.ZAR by
  CD location, streamed sounds (ST N1/N2) as VAG/VPK in VAGSTORE.ZAR, CSndInstance pool (48),
  CSndGroup (GROUPS), CSndJukebox + CSndSequence (sndjukeboxm.rdr), zAnim SOUND command.

## Results (p2.log = probe build with pad_w.txt; default.log = default build)
- Sound system start -> 16397; master volumes all 1024; HUDUI bank at sector 144474+768 -> IOP
  handle 0x1e1d00; mission banks m8_vce/m8_efx/m8_amb load; SMUS/VOICE/WEAPONS/TCM_ECHO/m8_svo/
  m8_smu have no .BNK (streamed sets) -> handle 0, as in the ELF.
- Menu: SND_THUNK on selection (MakeNextButtonActive), SND_TYPE per teletype letter, SND_SLIDE /
  SND_METAL from briefing anim SOUND commands. Probe: each play returns a handle (0x85000002..)
  and 989snd reports it ended after 3-40 frames (THUNK 38, SLIDE 14-16, TYPE 3-6, METAL 143).
- Mission: 450 groups, jukebox 61 stealth / 4 fight sequences; VAG streaming init -> 1; music
  streams start (sector 127440 at 60.6 s, 126686 at 70.1 s, 126867 at 77.8 s, group 1) and stay
  alive ~9.5 s each (one still-playing query every other frame); reload SND_M4_A1_RELOAD plays
  (ended after 24 frames). No IOP-side errors in the log.
- Front-end music: CallMusic's SOUND MUS_ST_SOCOM_THEME is streamed, and the front end never
  starts streaming (its UI_COMMAND VagStreaming is compiled as type 0 in dlgMenu, a no-op in the
  ELF too), so no menu music - ELF behaviour.

## Not working / not written
- Fire and impact sounds: zAnimSoundTick is written, but no in-mission anim ever reaches its
  SOUND command (no "anim ... SOUND" trace after the briefing): muzzle_m4SD (CALL_ANIMATION x4,
  SOUND 0x82 START|AT_NODE) and bullet_hit_* (SOUND 0x88) are not executed. Cause is on the
  weapon/anim side (CZKit::Fire's ActivateArg needs both firepoint nodes; activation not traced).
- Footsteps: CZSealBody::HandleSealStep (0x291b60) and HandleFootfallSound (0x2920c0) are
  stubs; HandleSealStep also needs GetVisualNode/GetDecalNode (zWeapon, non-void stubs).
- Headset (radio voice through the headset queue, HN sounds) offline: ftsGetHeadset is NULL.
- zAnimLoadSound (text-rdr parse) not written (anims load from ZARs).
