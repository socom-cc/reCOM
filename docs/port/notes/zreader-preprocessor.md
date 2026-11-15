# zReader text reader: file stack and preprocessor (2026-11-15, socom-port-zreader-fix)

The text-reader family of `src/gamez/zReader/zrdr_parse.cpp` compared with the reference ELF
instruction by instruction and rewritten from it: `zrdr_read` 0x23e540, `CRdrFile::ReadArray`
0x23e790, `ReadToken` 0x23e960, `_preproc_filter` 0x23ec80, `_eval_defined` 0x23f0d0,
`_get_pptoken` 0x23f2e0, `ValidateFormat` 0x23f440, `MakeUnion` 0x23f5e0, `CFileStack::pop`
0x23f6e0, `zrdr_sym::~zrdr_sym` 0x23f260. Found by `audit-unmarked-c2.md` ("found, not fixed").

## The record
- `fstack` 0x505ac0 is a Metrowerks `std::list<CBufferIO>`: the objects themselves, not pointers.
  Its node is 40 bytes (links, then the 32-byte `CBufferIO` at +8); `insert` 0x23f830 copy-constructs
  the element, `erase` 0x23f760 / 0x23fb20 run `~CBufferIO` and `~CFileIO` (both close) and free the
  node. Every push is at `begin()`, so the front is the file being read. No DWARF for `CFileStack`,
  `CBufferIO` or `zrdr_sym`; the layouts are from the code.
- `zrdr_symbols` 0x505ae0 is a `std::list<zrdr_sym>`; `zrdr_sym` has two strings, +0 (the name
  `_eval_defined` compares) and +4, both freed by its destructor (lines 240 / 242). The only
  references are `__sinit_zrdr_parse.cpp` (construct and register the destructor) and
  `_eval_defined` (read): nothing adds a symbol, so the list is always empty and `#ifdef` is
  always false. There is no `#define` in the reader: `_get_pptoken` knows only `ifdef`, `else`,
  `endif` and `include` (strings 0x44ffe8..0x450000); `#define`, `#if`, `#ifndef` are
  `pptoken_undef`, and the words after them are read as ordinary tokens.
- One read helper is inlined in every function (no symbol): a character from the front file; at the
  end of an included file it is closed and popped (`pop(true)`) and the read goes on in the
  including file; false at the end of the last file. The word tests use the MSL ctype table
  (0x466cc0, bit 8 = white space).
- `zrdr_read` reads the text file whenever the archives have no compiled reader of that name, not
  only with `ZRDR_FLAG_RAW`: with the flag clear it tries `CRdrArchive::FindRdr` first and falls
  through to the raw read when that finds nothing.

## Results (port before -> after)
| item | ELF | port before | result |
| --- | --- | --- | --- |
| `CFileStack::pop` 0x23f6e0 | front closed (or released), `erase(begin())` | erased the whole stack | FIXED: only the front element |
| `_eval_defined` 0x23f0d0 | symbol to the first white space, looked up by name, 1 when found | `while (fstack.size() > 2);` (a spin above two files), letters tested with `isalpha`, a different result | FIXED: as the ELF (always 0: no symbols) |
| `#include` in `_preproc_filter` 0x23ec80 | a local `CBufferIO` opened and copied into the list, then released | pushed the address of the local (dangling after return) | FIXED: the element is copied in (element model: objects) |
| `CFileStack::~CFileStack` 0x23fa70 | `erase(begin(), end())`: each element's `~CBufferIO` / `~CFileIO` | (pointers: nodes only) | EQUIVALENT-IMPLICIT: with `std::list<CBufferIO>` the implicit destructor does the same |
| `zrdr_sym::~zrdr_sym` 0x23f260 | frees +0 and +4 | no such type (`std::list<char *>`) | WRITTEN (zrdr_parse.cpp, `zrdr_sym` in zrdr.h); unreachable: the list is never filled |

Other differences found in the same family and fixed:
- `_get_pptoken`, `_eval_defined` and the include path tested `isalpha` where the ELF tests white
  space, so every directive came back as "undefined" and its words were read as tokens.
- `zrdr_read` returned NULL when the archives had no reader and the flag was clear (the ELF reads
  the text file), leaked the `new CBufferIO` and the rejected `CRdrFile`, set `length = 1` (the ELF
  copies only the type and the array) and erased the whole stack at the end (the ELF closes and
  erases the front).
- `ReadToken` returned 0 at the end of an included file (its reads did not pop), so the rest of the
  including file was lost; `ReadArray` would insert the previous node again when `ReadToken` returned 0 (the ELF inserts
  nothing then);
  `_preproc_filter`'s `#ifdef` / `#else` skips followed a different shape (tests on `fstack.size()`
  where the ELF pops), and its token values were 1, 2, 4, 8, 16 (ELF 0..4).
- `ValidateFormat`: written as the ELF's switch; it winds back the front file it started with.
- `zrdr_freearray` 0x23e3c0 (zrdr_main.cpp; frees a parsed reader's arrays, from `zrdr_free`,
  `~CRdrFile` and `CRdrFile::Pack`): its walk went one element past the end of every array
  (`i <= count`) and freed whatever lay there. No parsed reader was ever freed before (the raw read
  never happened), so it surfaced with the first one: `e3config.rdr` crashed in `zrdr_free` (TLB
  misses in `_free_r`) at the m8 load. Rewritten from the ELF (one recursion level unrolled there,
  written recursive); the ELF has no NULL test of the node either.

ELF quirks kept: `_get_pptoken`'s word buffer is not cleared (white space right after `#` compares
what the stack holds); an include path keeps its quotes (`#include "a.rdr"` looks for `"a.rdr"`
with the quotes and is ignored); an inner block's `#else` met while an outer block is skipped ends
the outer skip; a missing `#endif` or an unclosed quote at the end of the files never ends; the
quoted part of a word is not bounded; includes resolve against the last non-NULL path given to
`zrdr_read`.

Port deviations: the word / path buffers are one byte longer than the ELF's 768 (the ELF writes the
terminator after a 768th character one byte past them, into the caller's frame); the inlined read
is a file-local `static inline` helper; the member names of `zrdr_sym` are invented.

## Which disc files reach these paths
Every file of the demo disc image (archives `.ZAR` / `.ZED` and loose files; movies, sounds, IRX
and icons left out) was searched for `#include`, `#ifdef`, `#ifndef`, `#if`, `#else`, `#endif`,
`#define`, `#undef`: no reader uses any of them (one `#if` byte sequence inside the texture data of
`RUN/UI/ASSETLIB/LD/LD12/LD12_TXR.ZED`, not text). The archives hold compiled readers only (the
text parser is reached only through `zrdr_read`'s raw read; key names are plain text in the
archives, e.g. `mission.rdr` in `RUN/SP/M8/READERM.ZAR`).

Only two text readers are on the disc, both loose in the root and in no archive:
- `E3CONFIG.RDR` (9,903 bytes, CRLF, `;` comments, quoted names, no directive): read by
  `CLoadState::Init` (0x37f6e0) at every mission load, m8 included: 29 entries (mp1..mp12, m5, t2,
  a1, m6..m21), each a mission name with a multiplayer game type, time, rounds and player lists;
  only a network game uses them (`CLoadState::Tick`). The port never read it (NULL: not in an
  archive and no raw flag); it is now parsed as the ELF parses it.
- `NETWORK.RDR` (0 bytes): `CZNetwork::zNetInit` (0x3221b4); empty, so the load fails (NULL) as
  in the ELF; not reached offline in these runs.

So the raw text path (file stack push and erase, `ValidateFormat`, `ReadArray`, `ReadToken`,
`MakeUnion`, comments and quotes) is used by the disc (e3config.rdr in m8); `#include`, `#ifdef`,
`#else`, `#endif` and the pops of included files are used by no disc file: written, tested only
with the test hook's own files (below), untested on disc data. The menus read no text reader.
Readers missing from the archives (`dyntex.rdr` at boot, `lensflare.rdr` in m8) now also try the
disc as the ELF does and fail there (NULL, as before).

## Runs
Test hook `port/test-hooks/zreader` (with the state hook) serves its own text files from memory
through a `CBufferIO::Open` wrap: `ztest/main.rdr` includes `inc.rdr`, which includes `inc2.rdr`,
then `#ifdef ZT_SYM` / `#else` / `#endif`, `#include "quoted.rdr"` and `#define ZT_DEF 5`. A diag
trace at the start of `CFileStack::pop` gives the pops. Every run on HEAD 39bc4b05 + these files,
focus kept in every run, no STOP, no exception; screenshots untracked
(`build/port/screenshots/53-audit/*_zreader-*`).
- Before (HEAD b13e0497's zrdr_parse.cpp, same hook): the self-test parses `('zt_a' (1))` and
  stops: the directive is not recognised (letters tested instead of white space) and the parse
  ends with the first file; `e3config.rdr` -> NULL at the m8 load (never read).
- After (zr_m8, `-DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=999999`, 250 s): opens of `main.rdr`
  at stack depth 0, `inc.rdr` at depth 1, `inc2.rdr` at depth 2; pops with depth 3 then 2 at the
  ends of the included files; the quoted include asks for `ztest/"quoted.rdr"` and is skipped;
  parsed `('zt_a' (1) 'zt_inc' (7) 'zt_inc2' (9) 'zt_inc_after' (8) 'zt_b' ('two') 'zt_d' (4)
  'ZT_DEF' 5 'zt_e' (6.5))`: the `#else` part read, the `#ifdef` part skipped, the `#define`'s
  words read as tokens; symbols defined: 0 before and after (the ELF never adds one); stack depth 0
  after the read. `e3config.rdr` opened from the disc root and parsed: 29 entries, the same names
  as the file (mp1 FOOTBOMB 360 s 11 rounds, mp2 DEATHMATCH 240 s, ... m21), freed again. Intro
  movie skipped with CROSS, briefing cameras m8bs / m8tut1 with X; in the mission from 66.3 s to
  the end at 250.7 s (184 s), heap in use 23,046,628..23,049,620 B from 110 s to the end (steady).
- Front end (zr_fe, fake pad of mod-zui part 2, no hook): dlgMenu -> Options -> Audio, Video,
  Controller Selection, Controller Presets -> dlgMenu -> dlgHype -> dlgMenu; no STOP.
- Round trip (zr_rt, `port/test-hooks/state`, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`,
  800 s): eight missions and returns; in use at the briefing 18,666,948 B at return 1 and
  18,667,044 B at returns 2-8 (flat, the same figures as HEAD alone), largest free block 3,960,832 B
  at every return. HEAD 39bc4b05 alone (zr_hrt, two returns): in use 18,666,948 / 18,667,044 B,
  largest free block 3,985,408 B. The 24,576 B difference is one more break step during the
  mission load (arena 23,100,908 B against 23,076,332 B): `e3config.rdr`'s text buffer and parsed
  nodes live while `CLoadState::Init` reads it, as in the ELF. The menus' 2,598,384-byte archive
  buffer still fits at every return. At the first dlgMenu: 18,156,964 B in use and 8,867,840 B
  largest free in both (the boot is unchanged: the only new boot work is one failed disc open for
  `dyntex.rdr`).
- Default build (`default.sh`, no hooks, no fake pad): dlgMenu at 15.6 s, the main menu on screen.
