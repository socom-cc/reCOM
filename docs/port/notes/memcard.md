# Memory card: save and load (functional port)

Worker `socom-port-memcard`, 2026-11-15/16. The card layer (`port/compat/libmc.c`), the game's
save path (`CMemCard`, `CSaveManager`, `zar::CZAR` writes, `CSTable`, `CRdrFile::Insert`) and the
test hook `port/test-hooks/memcard`. All tests ran on the dedicated test card only, one card boot at
a time; every other boot runs with empty slots.

## What the demo saves, and when

The disc's menu scripts (`RUN/UI/READERC.ZAR`) hold the card logic as UI animations:

| script | animation | what it does |
| --- | --- | --- |
| `UIIntro.rdr` (via `uianim.rdr`) | `intro_onstart` | `MC_Init`, port 0, inserted? formatted? If not formatted: "Memory card (PS2) in slot 1 is not formatted. Do you want to format and create new data?" (buttons "No" = 1, "Yes" = 2), "Are you sure you want to format?", then `do_formatting`: `FormatMemCard`, `Ensure_MC_Dirs`. Formatted: the 300 KB free-space check. |
| `UIMemCardAnim.rdr` | `Ensure_MC_Dirs` | `chdir ..`, then `chdir BASCUS-97859SOCOM`, or `mkdir` + `chdir` + `MC_CreateIconFiles` + `SaveConfig BASCUS-97859SOCOM` |
| | `load_initial_config` | once per boot (valve `memcard_have_loaded_config`): "Loading preferences..." and `LoadConfig BASCUS-97859SOCOM`; no data / not inserted: a "press X" pop-up |
| | `save_and_leave` | "Would you like to save to the memory card (PS2)?", then inserted / formatted / 300 KB free, `Ensure_MC_Dirs`, `SaveConfig` |
| `dlgDebriefing.rdr` | `MemCheckSave`, `SaveGameOnListBox` | the career save: `SaveSavedGame <slot>` (`SaveGame<n>`) + `SaveConfig`, its own format question |
| `dlgMenu.rdr`, `dlgMenuMp.rdr`, `dlgPBMenu.rdr` | `MainMenuOnLoad`, `LoadGameOnListBox` | load a saved game from slot 1 or 2 |

**None of these is reachable in the demo's own flow.** `dlgIntroScreen` switches to the intro
cinematic at once (UIIntro's `intro_onstart` is never called), the options screen's TRIANGLE runs
`check_then_save_and_leave`, which only switches to `dlgMenu`, `dlgMenu` has Start and Options only
(its load animations are not on a button), and the success debrief's CROSS goes to the attract
screen (`MemCheckSave` is called only from `SaveFromReplay`, which nothing calls). So a normal
build never calls a card function: with a card in the slot the game boots, plays and goes through
the menus exactly as without one. The coordinator's items 7 (a normal build saving through the
game's screens) and 9 (a normal build meeting an unformatted card) cannot happen in the demo; the
hook below starts the same animations from the options screen instead.

What `SaveConfig` writes (`CSaveManager::Save`, version 1, a secured zar archive): the modules on
`theMemCard.m_config` - `CUIVarManager` (every PERSISTENT UI variable: in the demo the three audio
volumes SOUND_VOLUME, MUSIC_VOLUME, DIALOG_VOLUME once the audio screen was opened; the video /
controller variables once their screens were opened) and `CValveSaveManager` (persistent valves).
773 bytes with the three volumes. `CMemCard::SaveGame` (the career save, version 2) is never
reached.

Card layout after the game's own format and save (`sceMcGetDir`, run `save5`):

```text
/BASCUS-97859SOCOM/              (directory)
    icon.sys                  964 bytes   title "SOCOM:2002 Public Beta" (full-width Shift-JIS)
    LIST.ICO                50680 bytes   copied from the disc's RUN/ICONS
    COPYING.ICO             50680 bytes
    DELETING.ICO            50680 bytes
    BASCUS-97859SOCOM         773 bytes   the options save
free: 7995 KB right after formatting, 7843 KB with the files
```

## The card layer (`port/compat/libmc.c`)

ps2sdk's EE libmc under Sony's names. The game's own libmc (sceMcInit 0x171070, sceMcGetInfo
0x171be8, mceGetInfoApdx 0x171b90, sceMcChdir 0x171fc0, mceStorePwd 0x171f38, sceMcSync 0x171ab0)
speaks the newer MCSERV protocol (INIT 0xfe, GET_INFO 1; request words format / free / type at
+12 / +16 / +20, answers type / free / formatted at +0 / +4 / +144 of a 192-byte block). The pinned
ps2sdk (libmc as of commit 1269cb4) picks that protocol by itself ("XMC"; its `mcInit` ignores the
type argument) against the disc's MCSERV 2.01 / MCMAN 2.06 and reads the same words, so the card's
answers reach the game unchanged. The init trace names the protocol it bound (a `mcGetEntSpace`
probe, which ps2sdk refuses at once on the old protocol).

The "good card read as unformatted" defect reported earlier was not one: the card of those runs
was logged by PCSX2 itself as "8 MB, UNFORMATTED".

Result codes. The sync results (`*result`) come from the disc's Sony MCSERV, so they are Sony's
and pass through: 0 succeeded / same card, -1 new formatted card, -2 new unformatted card (or
not formatted), -4 no entry, -5 denied, -10 / -11 no card (an empty slot answers -11 with type 0).
`sceMcSync` returns 1 finished, 0 still running (mode 1), -1 nothing registered, as Sony's.
What the layer maps:

| call | ps2sdk | Sony / the layer |
| --- | --- | --- |
| any registration while another call is registered | that call's number (> 0) | -200 (Sony's PollSema answer) |
| any call without a bound client | -1 | -100 |
| `sceMcChdir` with a NULL or empty name | sends it | -210 (Sony) |
| `sceMcChdir` with a NULL `curDir` (the game always passes NULL) | its end function copies to NULL | the layer's own buffer (Sony's skips NULL) |
| `sceMcGetInfo` type / format words | asked only when given | always asked (the layer's own words when NULL), so the layer knows the card's last answer; free only when the game asks |
| `sceMcSync` with nothing registered and the layer unbound | -1 | -1, `*result` = -10 (port: a defensive "no card") |

Traces (`MC:`): the bind, each info answer when it changes (result, type, format, free, time),
failed calls (directory searches that find nothing excepted), short or empty writes, formats.

## The format rule

`sceMcFormat` forwards to ps2sdk's `mcFormat` only when `socom_port_memcard_format` is non-zero
**and** the layer's own last info reply for that port and slot was complete (result 0 / -1 / -2)
and said "PS2 card, not formatted". Otherwise it refuses (-1, traced) and `CMemCard::Format`
reports failure. `socom_port_memcard_format` is 0 in every build; only the memory-card test hook
sets it, for the dedicated test card the user allowed to be formatted. A card that reads as
formatted is never formatted. The test card was formatted once, by the game's own
`FormatMemCard` (run `fmt1`: 1542 ms, result 0).

`socom_port_memcard` is 1: normal builds use whatever card is in the slot (and, as above, the demo's
screens never touch it).

## Defects fixed on the save path (all from the ELF)

| where | ELF | was | now |
| --- | --- | --- | --- |
| `zrdr_file.cpp` `_resolveA` | 0x23c660 | loop without an end test, string offsets taken off arrays | the inverse of `_resolveB` (strings to the string table, arrays to the node block, an array after its children) |
| `zar_search.cpp` `CZAR::Insert(key, buf, size)` | 0x1db410 | a secured archive inverted the caller's buffer in place and wrote nothing (`CRdrFile::Insert` then read its own buffer inverted: endless pointer walks) | an inverted copy written, offset / size set, padding 'P' (0xaf secured) |
| `zar_search.cpp` `CKey::Write` | 0x1dc2d0 | wrote the name's first four characters and four bytes of the list object | name address, offset, size, child count (what `CKey::Read` takes back) |
| `zar_main.cpp` `CKey::fixupKey` | 0x1d8600 | the first child fixed up once per child | every child and grandchild |
| `util_stable.cpp` `CSTable::FindString` | 0x306040 | no answer when nothing matched, no empty-slot test | NULL |
| `util_stable.cpp` `CSTable::Pack` | 0x306300 | copied from the wrong buffer, kept and freed the wrong strings | strings moved into one buffer, users re-pointed by the fixup, old strings freed |
| `util_stable.cpp` `CSTable::Relocate` | 0x306500 | (worked) | ELF quirk kept: the table's entries are walked but not changed |
| `util_stable.cpp` `CSTable::ReleaseBuffer` | 0x3062b0 | `==` for `=`: never dropped | dropped (freed when owner) |
| `util_stable.cpp` `CSTable::CreateString` | 0x305e60 | new strings at the front | at the end; empty slots skipped |
| `port/compat/sce_iop.c` `sceOpen` / `sceRead` / `sceLseek` / `sceClose` | - | read-only `cdrom0:` files through ps2sdk's EE fio client, which does not speak the IOP FILEIO of the game's IOP image: the IOP gets the path 16 bytes short ("Unknown device 'NF;1'" for `cdrom0:\SYSTEM.CNF;1`), the open "works" and reads nothing; `CreateIconFiles` wrote empty icons | found with `sceCdSearchFile`, read by sector with the stream-safe CD read the game's `CFileCD` uses |

`CMemCard` / `CMemCardIO` (util_memcard.cpp) were compared with the ELF instruction by
instruction and needed no change (the port only initialises `Init`'s format word, which the ELF
leaves as it was on the stack).

## ELF quirk kept: the three card commands retry for ever

`zanim_menu.cpp`: in the ELF `UIFormatMemCard`, `UIMC_MkDir` and `UIMC_ChDir` return their
`CMemCard` call's result, and a false answer keeps the UI command running, so a failed format,
mkdir or chdir is tried again every frame for ever. The port keeps that (the coordinator restored it
at the merge; the worker's tree ended the commands after one try). Consequence in the port only: a
format the card layer refuses (any card but the dedicated test card, and every normal build) leaves
the "Formatting..." pop-up up for good (run `unf1`, made with the refusal: 3416 format attempts).
No screen the demo can reach runs these commands. The scripts use them only as statements, never as
IF conditions.

## Timings

An empty slot answers an info call in about 4.8 ms (12 polls, 58 ms in all, run `nocard2`); a
present card 0.2 to 28 ms, 69 to 95 ms for the first call after the card changed (it reads the
card's superblock, and the free count reads the FAT). The game polls only from the card
animations above (a few calls each), never per frame.

## Evidence (scratch `build/port/boot-memcard/`, logs untracked)

| run | build | shows |
| --- | --- | --- |
| `nocard2` | hook, layer forced on, empty slots | no-card path: "not inserted" pop-ups, X, no hang (item 5) |
| `unf1`, `unf3` | hook plan 0, test card unformatted, format off | PCSX2 "[8 MB, UNFORMATTED]", layer result -2 type 2 format 0, the game's format question, format refused; `unf3` with the one-try commands: no hang |
| `fmt1` | hook plan 1, format on | the game's FormatMemCard formats the card (once), free 7995 KB |
| `save3`, `save5` | hook plan 1 | `SaveConfig` (773 bytes, MUSIC_VOLUME 0.8), the directory listing, the icons (50680 bytes each after the disc-read fix) |
| `load1` | hook plan 2, a second boot | MUSIC_VOLUME 0.5 before `LoadConfig`, 0.8 after; the audio screen shows 0.8 |
| `fio4` | hook, empty slots | disc file read: LIST.ICO 50680 bytes |

## Not written / next

- The career save (`SaveSavedGame` / `LoadSavedGame`, `CMemCard::SaveGame` / `LoadGame`, the
  SavedGames list box) is unreachable in the demo and was not run.
- Whether to wire the card animations into the demo's reachable screens (a port deviation from
  the ELF's menus) is the user's decision; nothing here does it.
- `CRdrFile::Pack` / `Insert` were exercised with flat readers (UI variables, the valve list); deeper
  readers (`OnListSavedGames`' list) were not.
