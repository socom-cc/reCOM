# Stage 3: signatures in the release program (running note)

Step two of stage 3: `tools/release/signatures.py` carries a function's prototype (return type,
parameters, calling convention) from the prototype program `socom.elf` to its pair in the release
program `SCUS_971.34`, so that the decompiler shows members where it showed raw offsets. Tool by
`socom-release-signatures-s1`, review and check script by `socom-release-signatures-review-r2`;
applied, saved and confirmed by the coordinator. The names step is in `stage3-names.md`.

## What can be carried

From the whole-map plan (2026-11-26, read-only):

| Group | Functions |
|---|---|
| exact pairs with a prototype to carry | 2,485 |
| deviating pairs (the prototype's signature as a starting point; the plate says so) | 2,037 |
| prototype functions that still have Ghidra's default signature: nothing to carry | 4,082 |
| withheld | 629 |

Withheld: 352 map functions without a Ghidra function, 189 library pairs that are not exact, 24
thunks, 20 boundary differences, 15 unsure pairs, 14 for a missing type, 8 inside another
function, 4 flagged pairs, and 0x15a600, 0x15a500 and one whose counterpart is a thunk. 22 thunks
follow their target's signature without being written.

Nine types that prototypes name are not in the release program, because they lie outside the
`project` category that was copied: `/locale.h/lconv`, `/stat.h/stat`,
`/stdarg.h/__gnuc_va_list`, `/stddef.h/size_t`, `/stdint.h/intptr_t`, `/stdio.h/FILE`,
`/types.h/__off_t`, `/types.h/__pid_t`, `/types.h/ssize_t`.

## What the bridge does and does not carry

Read from the plugin's and Ghidra's own classes by the tool's author and again by the reviewer:

- The only writes are `set_function_prototype` and, for a deviating pair, `set_comment` for the
  plate. Parameter storage is always recomputed by Ghidra from the calling convention; the tool
  reads it back and compares it with the prototype's, parameter by parameter.
- The no-return flag and custom storage cannot be written. Three no-return differences are
  listed in the plan (0x1401c8, 0x422590, 0x423c78).
- The endpoint would rename a default-named function to the name in the text, so the tool sends
  the function's live name; no name, label or namespace changes.
- A prototype's return type and parameter names are carried as the prototype program has them,
  `undefined` and `param_N` included.

## The review

Verdict: safe to run the pilot. The reviewer's own model of the parser accepts all 4,522 planned
texts; a sample of 109 planned writes across 40 modules and all 43 of the pilot agree with both
programs. Its defects, none blocking:

1. After a stop, a prototype the program holds can be missing from the record (the signature is
   written in a first transaction, the convention in a second). Until this is fixed: after any
   stop the program is closed without saving.
2. The apply does not re-check a function's thunk flag before writing.
3. The tool's snapshot does not see bookmarks, locals, return storage or types added to the type
   manager; the reviewer's check script covers bookmarks, locals, parameters and `socom.elf`.
4. The type check does not model two parser rules (C primitive names resolve to built-ins first;
   `.conflict` suffixes are ignored); no planned type is affected today.

## Pilot: gamez/zArchive

Plan 771db22e..., one snapshot after every write.

| Run | Prototypes | Plates | Outcome |
|---|---|---|---|
| first write (0x1db360) | 1 | 0 | as planned; check clean; saved, confirmed |
| the other exact pairs | 8 | 0 | no stop, no change the run did not make; check clean; saved, confirmed |
| deviating pairs | 34 | 34 | no stop, no change the run did not make; check clean; saved, confirmed |

The decompiler before and after, in three functions: `zar::CZAR::Open` (0x1dacb0) went from 15 raw
offsets to 19 member accesses, `zar::CKey::Read` (0x1dd7c0) from 4 to 4, `zar::CZAR::Fetch`
(0x1dd3e0) from 1 to 2. No analysis ran in answer to a write. A plan of the names step made
afterwards sends nothing.

The record holds 43 rows of the kind `prototype`.

## Whole map

Plan 72381549... (made after the pilot and after the reviewer's defects were fixed in the tool:
the record stays truthful after a stop, the thunk flag is read again before each write, the type
check follows the parser's two rules; that change was not reviewed again). Batches of 500, a
snapshot after every ten writes. Each batch is checked before its save with the reviewer's
script against a baseline of every function's signature line, both programs' bookmarks and
`socom.elf`; the script also reads each written function's parameters and storage. Its baseline
holds locals only for the pilot's functions, so a local variable that Ghidra drops when a
signature is set would not be seen in these batches; the release program has no local that
anyone set, and the written functions that were probed have no stored local at all.

| Batch | Group | Prototypes | Plates | Outcome |
|---|---|---|---|---|
| 1 | exact | 500 | 0 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 2 | exact | 500 | 0 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 3 | exact | 500 | 0 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
