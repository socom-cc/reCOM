# Library pairs the comparison missed: the push-to-talk library, Medius, newlib (2026-11-28)

A check of the pairs that `socom-release-newnames-p2` proposed in `new-function-names-2.md` (its
`library` rows matched to a prototype copy, and its last section, contradictions with the map). The
proposals were checked by `socom-release-pairs-check-k2`, who wrote neither them nor the comparison tool
(`python tools/release/compare.py`, pairing by `socom-release-compare-c1`), at commit 99932466. The tracked
`function-map.tsv` equals a fresh rerun at that commit. Both executables were decoded with `tools/release/`
(masked words, calls, data operands with the release `$gp` 0x494670, float constants built by `lui`/`ori` or
loaded from data, argument registers read before written, callers found by a scan of the whole image). For
each pair I compared the ordered call list mapped through the map, the statics through `data-map.tsv`, the
float constants, the arguments, the callers and the place between paired neighbours. For the push-to-talk
client I also read the RPC command number, the send and receive sizes and the sync-reason byte of every
sender (both disassemblies of 0x437bf0 and 0x437cf0 also read in Ghidra, read-only). No new pair was
committed on similarity alone: the bodies of the rebuilt library have masked similarities of 0.02 to 0.55,
since the compiler changed. A trial rerun of the comparison with these rows added to `settled-pairs.tsv`
(scratch only) took all of them: 56 pairs settle as deviating, 1 as new, 5 as removed.

What the library looks like: the release links the same push-to-talk library (the LPC-10 codec, its f2c
helpers, the PTT client, the PTT server) in the same file order, rebuilt: within each file the functions
come in reverse order (`chanrd_`, `chanwr_`, `chanwr_0_`; `i_nint`, `r_sign`, `pow_ii`; the PTT client from
`PTT_ReleaseTalk` up to `PTT_Init`), and the PTT server file now comes before the codec. Small helpers were
inlined (`PTT_IsNewCallOk`, `scePcGetCounter0`, `lpcini_`). Two client calls are gone.

## Checked pairs

Class "map" is the class in today's map: `new` / `removed` means both sides stand unpaired.

| release | prototype | map | verdict | reason |
|---|---|---|---|---|
| 0x432fc0 | 0x3eb3a0 `analys_` | new / removed | same function, deviating | 14 callees in order, statics tau and buflim, float constants equal |
| 0x433810 | 0x3ebe70 `bsynz_` | new / removed | same, deviating | callees in order, static kexc, 11 float constants equal |
| 0x434680 | 0x3ecc30 `chanrd_` | new / removed | same, deviating | only call chanwr_0_; 5 arguments; caller lpc10_decode |
| 0x4346b0 | 0x3ecbd0 `chanwr_` | new / removed | same, deviating | only call chanwr_0_; 6 arguments; caller lpc10_encode |
| 0x4346e0 | 0x3ec850 `chanwr_0_` | new / removed | same, deviating | statics iblist and bit; callers chanrd_, chanwr_ |
| 0x435040 | 0x3ecc90 `dcbias_` | new / removed | same, deviating | 3 arguments; caller analys_; file order |
| 0x4351d0 | 0x3ecda0 `decode_` | new / removed | same, deviating | 9 callees in order, 7 statics paired |
| 0x435fd0 | 0x3edd80 `deemp_` | new / removed | same, deviating | its four float constants equal; caller synths_ |
| 0x4360b0 | 0x3edf10 `difmag_` | new / removed | same, deviating | 8 arguments; caller tbdm_; file order |
| 0x4361e0 | 0x3ee180 `dyptrk_` | new / removed | same, deviating | 7 float constants equal; caller analys_ |
| 0x436640 | 0x3ee790 `encode_` | new / removed | same, deviating | 5 statics paired; pow_ii; caller lpc10_encode |
| 0x436c80 | 0x3eeec0 `energy_` | new / removed | same, deviating | sqrtf; 3 arguments; caller analys_ |
| 0x436de0 | 0x3ef160 `i_nint` | new / removed | same, deviating | 7 runtime calls in order; 3 callers agree |
| 0x436e70 | 0x3ef0b0 `r_sign` | new / removed | same, deviating | 2 arguments; callers onset_, vparms_ |
| 0x436ed0 | 0x3eefb0 `pow_ii` | new / removed | same, deviating | 2 arguments; callers decode_, encode_ |
| 0x436f70 | 0x3ef230 `ham84_` | new / removed | same, deviating | static dactab; caller decode_ |
| 0x437030 | 0x3ef370 `hp100_` | new / removed | same, deviating | 6 float constants equal; caller prepro_ |
| 0x437120 | 0x3ef560 `invert_` | new / removed | same, deviating | float constants equal; caller analys_ |
| 0x437550 | 0x3efa20 `irc2pc_` | new / removed | same, deviating | sqrtf; 5 arguments; caller synths_ |
| 0x4379b0 | 0x3efc40 `ivfilt_` | new / removed | same, deviating | 5 arguments; caller analys_; file order |
| 0x437b10 | 0x3f12c0 `PTT_ReleaseTalk` | new / removed | same, deviating | RPC 7, sync reason 5; WorkerThread's two calls agree |
| 0x437bf0 | 0x3f11f0 `PTT_PushToTalk` | new / (paired with 0x437cf0) | same, deviating | RPC 6, 4 bytes in and out, sync reason 4 |
| 0x437cf0 | 0x3f11f0 `PTT_PushToTalk` | unsure | not the same function | it sends RPC 4 with sync reason 3: the prototype's `PTT_SetChannel` |
| 0x437cf0 | 0x3f1040 `PTT_SetChannel` | - / removed | same, deviating | RPC 4, 4 bytes in and out, sync reason 3; place in WorkerThread agrees |
| 0x437ed0 | 0x3f0e60 `PTT_JoinGame` | unsure | same, deviating | RPC 2 (20 bytes in became 24), sync reason store moved; first call of WorkerThread |
| 0x4381d0 | 0x3f0b30 `PTT_Sync` | unsure | same, deviating | 5 callees in order; callers Init, WorkerThread |
| 0x4382c0 | 0x3f0370 `PTT_Heartbeat` | unsure | same, deviating | its string, RPC 9, callees in order; caller CZNetVoice::Tick |
| 0x438b80 | 0x3f1380 `lpc10_decode` | unsure | same, deviating | callees chanrd_, decode_, synths_ |
| 0x438c20 | 0x3f1450 `lpc10_encode` | unsure | same, deviating | callees prepro_, analys_, encode_, chanwr_ |
| 0x438ce0 | 0x3f1a00 `init_lpc10_decoder_state` | new / removed | same, deviating | lpcini_ inlined; callers agree |
| 0x438f30 | 0x3f15b0 `init_lpc10_encoder_state` | new / removed | same, deviating | lpcini_ inlined; float constants 1, 20; callers agree |
| 0x439310 | 0x3f1c70 `lpfilt_` | new / removed | same, deviating | its 16 float coefficients equal |
| 0x439600 | 0x3f21b0 `median_` | new / removed | same, deviating | 3 arguments; caller decode_ |
| 0x439670 | 0x3f22c0 `mload_` | new / removed | same, deviating | 6 arguments; caller analys_; file order |
| 0x43a040 | 0x3f2670 `onset_` | new / removed | same, deviating | r_sign; float constants equal |
| 0x43a3a0 | 0x3f2b00 `pitsyn_` | new / removed | same, deviating | 9 callees in order; float constants equal |
| 0x43b270 | 0x3f37e0 `placea_` | new / removed | same, deviating | i_nint; caller analys_ |
| 0x43b740 | 0x3f41f0 `placev_` | new / removed | same, deviating | same argument registers; caller analys_; file order |
| 0x43ba10 | 0x3f47c0 `preemp_` | new / removed | same, deviating | 5 arguments; caller analys_ |
| 0x43bb70 | 0x3f4890 `prepro_` | unsure | same, deviating | calls hp100_; caller lpc10_encode |
| 0x43bbb0 | 0x3f48f0 `random_` | new / removed | same, deviating | 1 argument; caller bsynz_; file order |
| 0x43bc30 | 0x3f49d0 `rcchk_` | new / removed | same, deviating | float constant equal; caller analys_ |
| 0x43bd50 | 0x3f4b10 `synths_` | new / removed | same, deviating | callees pitsyn_, irc2pc_, bsynz_, deemp_ |
| 0x43c140 | 0x3f4f20 `tbdm_` | new / removed | same, deviating | difmag_ / fptosi sequence |
| 0x43c4e0 | 0x3f5430 `voicin_` | new / removed | same, deviating | 7 callees in order, static vdcl, float constants equal |
| 0x43cef0 | 0x3f6090 `vparms_` | new / removed | same, deviating | 5 callees in order; caller voicin_ |
| 0x3d4ea0 | 0x3b4cb0 `MediusCreateMessageID` | unsure | not the same function | a request function (NetSendMessage), a third copy of the GetTotalGames / GetTotalChannels body |
| 0x3d41ac | 0x3b4cb0 `MediusCreateMessageID` | new / (paired with 0x3d4ea0) | same, deviating (immediates only) | operations 1.000, the same callees; wrap 0x200 -> 999; the prototype's own slot |
| 0x423fa0 | 0x3e07b8 `__sfmoreglue` | new / removed | same, deviating | between the same paired neighbours; callees and caller agree |
| 0x424018 | 0x3e0828 `__sfp` | new / removed | same, deviating | same neighbours; callees __sinit, __sfmoreglue |
| 0x424130 | 0x3e0918 `_cleanup` | new / removed | same, deviating | same neighbours; _cleanup_r(_impure_ptr) |
| 0x425300 | 0x3e1a70 `_setlocale_r` | new / removed | same, deviating | same neighbours; strcmp x2; caller setlocale |
| 0x4253a0 | 0x3e1b08 `setlocale` | new / removed | same, deviating | same neighbours; the reentrant call |
| 0x426618 | 0x3e2d48 `__malloc_lock` | new / removed | same, deviating | same neighbours and allocator callers; the empty hook became a semaphore lock |
| 0x426698 | 0x3e2d50 `__malloc_unlock` | new / removed | same, deviating | as __malloc_lock |
| 0x427690 | 0x3e3d08 `_mprec_log10` | new / removed | same, deviating | same neighbours; __mprec_tens, dpmul |
| 0x427700 | 0x3e3d78 `_printf_r` | new / removed | same, deviating | same neighbours; _vfprintf_r |
| 0x428c68 | 0x3e5208 `_signal_r` | new / removed | same, deviating | same neighbours; caller signal |
| 0x428dc0 | 0x3e5388 `__sigtramp_r` | new / removed | same, deviating | same neighbours; caller __sigtramp |
| 0x428e78 | 0x3e5468 `signal` | new / removed | same, deviating | same neighbours; the reentrant call |
| 0x428ea0 | 0x3e5498 `_init_signal` | new / removed | same, deviating | same neighbours; the reentrant call |
| 0x428ec0 | 0x3e54c0 `__sigtramp` | new / removed | same, deviating | same neighbours; the reentrant call |
| 0x428f58 | 0x3e5568 `_sprintf_r` | new / removed | same, deviating | same neighbours; vfprintf |
| 0x42aeb8 | 0x3e75d8 `strtodf` | new / removed | same, deviating | between strtod and strtok; strtod, dptofp. The proposals name it `strtof`; the prototype's name is `strtodf` |

The other pairs of the PTT client the map already commits to agree on command and sync reason
(`PTT_LeaveGame` 3 / 2, `PTT_QueryWANAddress` 13 / 8, `PTT_Status` 6, `PTT_HeartbeatPrepare` 8,
`PTT_Destroy` 11, `PTT_Init` 10) and on callees (`_PTT_SyncCallback`, `_PTT_HeartbeatCallback`): confirmed,
no row needed. The cross-check (step 4 of the checker brief) over every pair above: the paired callers and
callees correspond, and no release or prototype function is in two pairs (the two counterparts that move,
`PTT_PushToTalk` and `MediusCreateMessageID`, leave 0x437cf0 for `PTT_SetChannel` and 0x3d4ea0 for new).
The caller differences all have one cause each: `CZNetVoice::RemoteSMUpdateCallback` calls nothing in the
release (so `PTT_SetChannel`, `PTT_JoinGame` and `PTT_Sync` lose that caller); `Permit` and
`HandleNewIPBuf` dropped `PTT_PermitWANAddress` + `PTT_Sync`, and `Init` dropped `PTT_DebugForceVolume` +
`PTT_Sync`; `exit` no longer calls `_cleanup`; the release adds `malloc`, `free`, `realloc`, `memalign` and
`calloc` wrappers that take the allocator lock. The release `MediusCreateMessageID` has no caller: each of
its 67 prototype callers is paired, and none of them calls it any more.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here. The same rows, tab-separated, are in
the scratch folder of this check (`settled-rows.tsv`).

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x432fc0 | 0x3eb3a0 | analys_: the same 14 callees in the same order (preemp_ ... rcchk_); statics tau, buflim (data map); float constants equal; caller lpc10_encode; rebuilt libptt copy, functions of a file in reverse order | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x433810 | 0x3ebe70 | bsynz_: callees random_, random_, sqrtf, random_, sqrtf in order; static kexc (data map); its 11 float constants equal (6.928, 342, 2000 ...); caller synths_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x434680 | 0x3ecc30 | chanrd_: calls only chanwr_0_; 5 arguments; caller lpc10_decode; chanwr.c's three functions in reverse order | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4346b0 | 0x3ecbd0 | chanwr_: calls only chanwr_0_; 6 arguments; caller lpc10_encode | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4346e0 | 0x3ec850 | chanwr_0_: statics iblist and bit (data map); callers chanrd_ and chanwr_; no calls | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x435040 | 0x3ecc90 | dcbias_: 3 arguments, no calls; caller analys_; between chanwr.c and decode_ in the library's file order | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4351d0 | 0x3ecda0 | decode_: callees ham84_ x2, fptosi, median_ x3, pow_ii x2, fptosi in order; statics corth, detau, detab7, descl, deadd, qb, nbit (data map); caller lpc10_decode | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x435fd0 | 0x3edd80 | deemp_: float constants 1.9998, 2.0925, 0.585, 2.5 equal; 3 arguments; caller synths_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4360b0 | 0x3edf10 | difmag_: 8 arguments, no calls; caller tbdm_; between deemp_ and dyptrk_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4361e0 | 0x3ee180 | dyptrk_: float constants equal (0.984375, 16, 128 ...); caller analys_; between difmag_ and encode_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x436640 | 0x3ee790 | encode_: statics enctab, enadd, enscl, enbits, entab6 (data map); pow_ii last; caller lpc10_encode | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x436c80 | 0x3eeec0 | energy_: calls sqrtf; 3 arguments; caller analys_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x436de0 | 0x3ef160 | i_nint: callees fptodp, dpadd, floor, fptodp, dpsub, floor, dptoli in order; callers placea_, voicin_, vparms_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x436e70 | 0x3ef0b0 | r_sign: 2 arguments, no calls; callers onset_, vparms_; the f2c helpers in reverse order (i_nint, r_sign, pow_ii) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x436ed0 | 0x3eefb0 | pow_ii: 2 arguments, no calls; callers decode_, encode_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x436f70 | 0x3ef230 | ham84_: static dactab (data map); 3 arguments; caller decode_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437030 | 0x3ef370 | hp100_: float constants equal (1.85908, 0.90243, 0.9417 ...); 4 arguments; caller prepro_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437120 | 0x3ef560 | invert_: float constants equal; caller analys_; between hp100_ and irc2pc_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437550 | 0x3efa20 | irc2pc_: calls sqrtf; 5 arguments; caller synths_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4379b0 | 0x3efc40 | ivfilt_: 5 arguments, no calls; caller analys_; last codec file before the PTT client | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437b10 | 0x3f12c0 | PTT_ReleaseTalk: RPC command 7, nothing in, 4 bytes out, sync reason 5, as in the prototype; WorkerThread calls it at the same two places; PTT_IsNewCallOk inlined | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437bf0 | 0x3f11f0 | PTT_PushToTalk: RPC command 6, 4 bytes in and out, sync reason 4, as in the prototype; WorkerThread calls it at the same place; the map had paired 0x437cf0 with it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437cf0 | 0x3f1040 | PTT_SetChannel, not PTT_PushToTalk: RPC command 4, 4 bytes in and out, sync reason 3, as the prototype's SetChannel (PushToTalk sends 6, DebugForceVolume 12); WorkerThread calls it after JoinGame as before; RemoteSMUpdateCallback no longer calls it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x438ce0 | 0x3f1a00 | init_lpc10_decoder_state: lpcini_ inlined (stores 10, 180, 1 into contrl_); callers create_lpc10_decoder_state, PTT_Heartbeat | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x438f30 | 0x3f15b0 | init_lpc10_encoder_state: lpcini_ inlined (stores 10, 180, 1 into contrl_); float constants 1, 20; callers create_lpc10_encoder_state, PTT_Heartbeat | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x439310 | 0x3f1c70 | lpfilt_: its 16 float coefficients equal; caller analys_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x439600 | 0x3f21b0 | median_: 3 arguments, no calls; caller decode_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x439670 | 0x3f22c0 | mload_: 6 arguments, no calls; caller analys_; between median_ and onset_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43a040 | 0x3f2670 | onset_: calls r_sign; float constants equal; 8 arguments; caller analys_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43a3a0 | 0x3f2b00 | pitsyn_: callees fptosi x2, logf x2, expf, logf x3, expf in order; float constants equal; caller synths_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43b270 | 0x3f37e0 | placea_: calls i_nint; caller analys_; between pitsyn_ and placev_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43b740 | 0x3f41f0 | placev_: no calls; the same argument registers; caller analys_; between placea_ and preemp_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43ba10 | 0x3f47c0 | preemp_: 5 arguments, no calls; caller analys_; before prepro_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43bbb0 | 0x3f48f0 | random_: 1 argument, no calls; caller bsynz_; between prepro_ and rcchk_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43bc30 | 0x3f49d0 | rcchk_: 3 arguments, its float constant equal; caller analys_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43bd50 | 0x3f4b10 | synths_: callees pitsyn_, irc2pc_, bsynz_, deemp_ in order; caller lpc10_decode | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43c140 | 0x3f4f20 | tbdm_: callees difmag_, fptosi x3 alternating as in the prototype; caller analys_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43c4e0 | 0x3f5430 | voicin_: callees vparms_, i_nint x5, sqrtf in order; static vdcl (data map); float constants equal (3000, 63, 64 ...); caller analys_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43cef0 | 0x3f6090 | vparms_: callees r_sign x2, i_nint x3 in order; caller voicin_; last function of the library | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x437ed0 | 0x3f0e60 | PTT_JoinGame: RPC command 2, 8 bytes out (20 bytes in became 24); WorkerThread calls it first as before; RemoteSMUpdateCallback no longer calls it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4381d0 | 0x3f0b30 | PTT_Sync: callees WaitSema, PollSema, SignalSema, memcpy, SignalSema in order; callers Init and WorkerThread (Permit, HandleNewIPBuf, RemoteSMUpdateCallback no longer call it) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4382c0 | 0x3f0370 | PTT_Heartbeat: its string 'PTT_Heartbeat: only %d/%d frames processed'; RPC command 9; the same callees in order (scePcGetCounter0 inlined as mfpc); caller CZNetVoice::Tick | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x438b80 | 0x3f1380 | lpc10_decode: callees chanrd_, decode_, synths_; caller PTT_Heartbeat | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x438c20 | 0x3f1450 | lpc10_encode: callees prepro_, analys_, encode_, chanwr_; caller PTT_Heartbeat | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x43bb70 | 0x3f4890 | prepro_: calls hp100_; 3 arguments; caller lpc10_encode; between preemp_ and random_ | socom-release-pairs-check-k2 | 2026-11-28 | | |
| removed | 0x3f0a50 | PTT_IsNewCallOk inlined: its WaitSema, sceSifCheckStatRpc, SignalSema, PollSema, SignalSema sequence opens every release PTT RPC sender; no function of its own in the release's PTT client | socom-release-pairs-check-k2 | 2026-11-28 | | |
| removed | 0x3f0a40 | scePcGetCounter0 inlined: the release PTT_Heartbeat reads the counter (mfpc) three times where the prototype called it three times | socom-release-pairs-check-k2 | 2026-11-28 | | |
| removed | 0x3f1530 | lpcini_ inlined: both release init_lpc10_*_state store 10, 180, 1 into contrl_ where the prototype called it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| removed | 0x3f0d80 | PTT_PermitWANAddress: no release function sends PTT command 14; its callers CZNetVoice::Permit and HandleNewIPBuf no longer call it (HandleNewIPBuf keeps PTTServer_PermitWANAddress) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| removed | 0x3f1110 | PTT_DebugForceVolume: no release function sends PTT command 12; its caller CZNetVoice::Init no longer calls it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x3d41ac | 0x3b4cb0 | MediusCreateMessageID: the same 39 instructions (operations 1.000), callees iTerminateString x2, iCreateAndAllocateMessageID; only the counter's wrap (0x200 -> 999) and address differ; between MediusGetGameListFilter and MediusReassignCallbackChatFwdMessageCallback as in the prototype; uncalled in the release (none of the 67 paired callers calls it); the map had paired 0x3d4ea0 with it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x3d4ea0 | new | a third copy of the MediusGetTotalGames / MediusGetTotalChannels request body with its own callback slot 0x44c314 (those two keep 0x44c30c / 0x44c310, paired in the data map); the prototype has no function between MediusGetTotalChannels and lgAudInit; caller RefreshRoomPlayerList only; was paired (unsure) with MediusCreateMessageID, which is 0x3d41ac | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x423fa0 | 0x3e07b8 | __sfmoreglue: between std and __sfp on both sides; callees _malloc_r, memset; caller __sfp | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x424018 | 0x3e0828 | __sfp: between __sfmoreglue and _cleanup_r on both sides; callees __sinit, __sfmoreglue | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x424130 | 0x3e0918 | _cleanup: between _cleanup_r and __sinit on both sides; _cleanup_r(_impure_ptr); exit no longer calls it | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x425300 | 0x3e1a70 | _setlocale_r: between _fwalk and _localeconv_r on both sides; callees strcmp x2; caller setlocale | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x4253a0 | 0x3e1b08 | setlocale: between _localeconv_r and localeconv on both sides; _setlocale_r(_impure_ptr, ...) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x426618 | 0x3e2d48 | __malloc_lock: between memset and __malloc_unlock on both sides; called by the same allocator functions (plus the release's malloc, free, realloc, memalign, calloc); the empty prototype hook now takes __sce_sema_id | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x426698 | 0x3e2d50 | __malloc_unlock: between __malloc_lock and _Balloc on both sides; the same callers; now signals __sce_sema_id | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x427690 | 0x3e3d08 | _mprec_log10: between _ratio and _printf_r on both sides; __mprec_tens and dpmul | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x427700 | 0x3e3d78 | _printf_r: between _mprec_log10 and printf on both sides; calls _vfprintf_r | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x428c68 | 0x3e5208 | _signal_r: between _init_signal_r and _raise_r on both sides; calls _init_signal_r; caller signal | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x428dc0 | 0x3e5388 | __sigtramp_r: between _raise_r and raise on both sides; calls _init_signal_r; caller __sigtramp | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x428e78 | 0x3e5468 | signal: between raise and _init_signal on both sides; _signal_r(_impure_ptr, ...) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x428ea0 | 0x3e5498 | _init_signal: between signal and __sigtramp on both sides; _init_signal_r(_impure_ptr) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x428ec0 | 0x3e54c0 | __sigtramp: between _init_signal and _kill_r on both sides; __sigtramp_r(_impure_ptr, ...) | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x428f58 | 0x3e5568 | _sprintf_r: between _getpid_r and sprintf on both sides; calls vfprintf | socom-release-pairs-check-k2 | 2026-11-28 | | |
| 0x42aeb8 | 0x3e75d8 | strtodf (the prototype's name; proposed as strtof): between strtod and strtok on both sides; strtod then dptofp | socom-release-pairs-check-k2 | 2026-11-28 | | |

Rows by kind: 62 pairs (39 of the proposals' library rows, among them the correction 0x437cf0 =
`PTT_SetChannel`; 6 unsure pairs of the same library confirmed; `MediusCreateMessageID` moved to
0x3d41ac; 16 newlib pairs), 1 new (0x3d4ea0), 5 removed. In the trial rerun these also turned
`_cleanup_r` (0x424110, unsure) into a deviating pair by call and slot (I checked it: `_fwalk(reent,
fflush)` on both sides), and gave the exact pairs `MediusGetTotalGames` (0x3d4d60) and
`MediusGetTotalChannels` (0x3d4e00) the flag `ambiguous`, because the now unpaired 0x3d4ea0 has the same
masked body. Their callback slots decide them (0x44c30c and 0x44c310, both paired in the data map; 0x3d4ea0
uses 0x44c314), so both pairs stand.

## What stays new, what stays removed, what is not settled

Stays new (the prototype has no such function; the proposals' names stay proposals):

- `setjmp` 0x428b38 and `longjmp` 0x428b90 (between `_sbrk_r` and `_init_signal_r`), `_vsprintf_r` 0x42ed20
  (after `vsprintf`): the prototype's newlib has neither.
- The SCE libcdvd stream calls 0x16f008 to 0x16f380 (`sceCdStInit` ... `sceCdStream`): no `sceCdSt*`
  function in the prototype.
- SCE libusbkb 0x43d578 to 0x43e940: the prototype had its own game-side `sceUsbKeybd*` functions
  (0x21b870 to 0x21ba10, removed, see `zInput.md`), a different implementation of other calls. The map's two
  earlier settled rows (0x43d808, 0x43dcf0 new) stand.
- The ezNetCnf client 0x431b88 to 0x431ed0 and `lgAudPrepareForReboot` 0x3d6350: no such function in the
  prototype.
- 0x3d4ea0, the third Medius request of the GetTotalGames family (callback slot 0x44c314); which request it
  sends is not known, so it has no name.

Stays removed: in the push-to-talk library `PTT_IsNewCallOk`, `scePcGetCounter0`, `lpcini_` (inlined),
`PTT_PermitWANAddress` and `PTT_DebugForceVolume` (gone, with their calls); in newlib `_puts_r`, `puts` and
`strncat`, for which no release function is left unpaired in that range (I did not search further).

Every prototype function of the push-to-talk library (0x3eb3a0 to 0x3f6fd0) now has a counterpart or a
reason in the table above.

Not settled here:

- Data. The pairs above imply data pairs the data map holds as removed or unpaired; read from the operands
  of paired instructions: the PTT client's `g_buffer` 0x5630c0 = 0x58e000, `g_syncReason` 0x476c98 =
  0x48ebf4, `g_permitSemaphore` 0x476c7c = 0x48ebd8, `g_syncSemaphore` 0x476c80 = 0x48ebdc, the codec's
  `contrl_` 0x5754d0 = 0x5a0410, and Medius's `MsgCounter.0` 0x43ba30 = 0x44c324 (the counter of
  `MediusCreateMessageID`, in its old place between `gpfClientConnectCallback` and `devicechanged`). A
  rerun of the data map after these rows may take them by itself; otherwise they are for a data checker
  (`settled-data.tsv`), not for this note.
- Whether `__malloc_lock` / `__malloc_unlock` should carry a flag: the prototype's are empty hooks
  (8 bytes) and the release's lock a semaphore. The identity is clear (the slot, the name the allocator
  calls); the body is new code.
- The names of the release-only functions above, and the class `exact` for none of these pairs: every body
  changed with the compiler.
