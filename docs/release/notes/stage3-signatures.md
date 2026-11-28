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
| 4 | exact | 500 | 0 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 5 | exact | 476 | 0 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 6 | deviating | 500 | 500 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 7 | deviating | 500 | 500 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 8 | deviating | 500 | 500 | full batch, no stop, no change the run did not make; check clean; saved, confirmed |
| 9 | deviating | 503 | 503 | full batch, no stop, no change the run did not make (the end of the plan); check clean; saved, confirmed |

The pass is complete (2026-11-26): a dry run of the plan for both groups sends nothing, and a
plan of the names step made afterwards sends nothing either. The record holds 4,522 rows of the
kind `prototype` (2,485 exact pairs, 2,037 deviating pairs with their plate flag), 29,702 rows in
all, every one saved. No run stopped, no analysis answered a write, and no function's signature,
name or body changed that a run did not write; 22 thunks follow their targets as predicted.

## What is left without a signature

Of the 6,991 functions of the game and engine modules, 4,118 have a signature now. The others:

- 2,215 pair with a prototype function whose signature is still Ghidra's default (about three
  in four of them exact pairs), `gamez/zUI` most of all (390 of its 530). A first look at them: their
  mangled symbols carry the class and every parameter type, for example
  `PrepModels__9CGameMenuFRC14CGameDlgDesign`; the return type and whether a member is static
  are not in the name. Nothing was derived from the symbols in this pass.
- 481 are new in the release and have no counterpart.
- 177 are withheld (no Ghidra function at the map start, a differing body, a flagged pair, a
  missing type).

No module has a signature on every function. `gamez/zArchive`, `gamez/zGraph` and
`gamez/zConsole` had everything that could be carried before the deviating group; every module
has it now.

## After the function starts

The function-starts step (`stage3-starts.md`) made 382 functions, the names step named them, and
every library is now named by its place. A new plan of the whole map (1908fcc1...) carried, in
two runs with the same checks as before, the prototypes that had become possible:

| Run | Group | Prototypes | Plates | Outcome |
|---|---|---|---|---|
| 10 | exact | 149 | 0 | no stop, no change the run did not make; check clean; saved, confirmed |
| 11 | deviating | 49 | 49 | no stop, no change the run did not make; check clean; saved, confirmed |

The deviating group holds 14 library functions named by their place (`strtok`, `strtok_r`,
`DMEmalloc`, `PTTServer_Start` and others); the coordinator read their planned prototypes before
the run. The record holds 4,720 rows of the kind `prototype` (2,634 exact pairs, 2,086 deviating).
A dry run for both groups sends nothing, and a names plan made afterwards sends nothing.

Not applied: the group `mangled` (79 prototypes derived from the mangled symbol), which waits for
a review, and what placeholder types would add to it, which waits for the user's decision.

## Prototypes derived from the mangled symbol

Decided by the user on 2026-11-27: close the gap of the functions whose prototype counterpart has
no signature with the evidence the ELF holds. Their Metrowerks symbols carry the class and every
parameter type. `tools/release/mwmangle.py` (a port of the prototype tools' demangler; all 6,844
mangled function symbols of the prototype ELF parse and mangle back, and an independent demangler
the reviewer wrote agrees on every one) and `tools/release/mangledsig.py` derive a prototype for
the group `mangled` of the signatures tool. Tool by `socom-release-mangle-m1`, review by
`socom-release-mangled-review-r4`.

What is derived: the parameter types from the name; `this` from ordered evidence (constructor or
destructor, const member, a slot in a vtable, free function, a namespace known as one, and last
the code reading the register after the declared ones); a return type only for constructors,
destructors, conversion operators and vtable-slot overrides that agree; otherwise `undefined`. Each
plate says the signature is derived, by which evidence, and where the receiver rests on the code
alone.

The first review said do not apply, and was right. A function that returns a structure takes a
hidden pointer to the return buffer in a0, which moves `this` and every argument by one; the rules
that decide from the name never looked at the code, and nine of the 79 entries planned then were
wrong. The author's agreement check could not show it: the prototype program has no
structure-returning function with a signature (29 of the 30 that DWARF knows were left unsigned,
which is how they came into this group). A class passed by value can also travel by address. Since
the fix an entry is withheld, under every rule, when the release code reads an argument register
beyond the predicted ones, when the counterpart's DWARF record returns a class by value, when a
function other than a constructor or destructor returns its entry a0, when a named type by value
is not proven an enum, and when the first access through a0 is a store. The second review read
all 61 remaining entries against the release code and their callers (no caller passes a stack
buffer in a0 or sets a register beyond the predicted ones) and would withhold none.

Applied in five batches (1, 4, 10, 20, 26), a snapshot after every write, each checked with the
reviewer's script (the signature line, parameters and storage, the plate clause, no `in_aN` left
in the decompiler) before its save: 61 prototypes and 61 plates, 35 on exact pairs and 26 on
deviating ones, no stop, no change a run did not make. In the decompiler `CBBox::GetIntersect`
went from no member access to 14 and `CSnd::CalcVolPan` from 3 raw offsets to 5 member accesses.
The record marks these values `[derived from the mangled symbol]`.

Why only 61 of 2,215: 1,311 are withheld for a receiver class and 715 for a parameter type that
exists in neither program or whose name the endpoint's parser cannot read (a comma in a template
name), 168 because `this` is undecided, 131 for a possible hidden argument. Empty placeholder
types for 284 of the missing names would bring the group to about 865; a plan and a tool for them
exist (`tools/release/placeholders.py`), not used: the user has not decided, and the reviewer
found one more defect in its apply path. Left open by the review: a function that returns a class,
has no DWARF record, never returns a0 and reads nothing beyond the predicted registers would pass
the rules; for these 61 the callers were read by hand.

## Placeholder types

Agreed by the user on 2026-11-27. The symbols name classes and types that exist in neither
program and have no debug record; a function whose `this` or pointer parameter is of such a type
could get no signature. `tools/release/placeholders.py` made an empty structure for each name that
can be declared safely: 284 types (244 under `/project`, 14 under `/project/zdb`, the rest in the
scopes their names carry). Each is a structure without members, shown as one byte, packed as the C
parser makes it; it claims no layout. A later real layout has to switch packing off and grow the
same type in place; deleting and recreating it would turn every parameter that names it
`undefined`. They are local to the release program: the prototype and the archive do not have
them.

Not made: 214 names that are not C identifiers (template instances, unnamed scopes), 52 that are
passed by value (an enum or a class, size unknown), 7 that equal an existing type name when case
is ignored (the endpoint that moves a type to its category searches without regard to case and
takes the first hit, so such a move could have taken the existing type).

The reviewer's defect in the apply path (a successful import was read as a failure because the
answer always carries an empty `error` key) was fixed by the coordinator before any use; the first
real import answered in exactly that shape. Applied in four batches (1, 9, 100, 174), one type at
a time inside each. The tool compares the whole type table around every write; the coordinator
also compared the whole type list of both programs before and after each batch with a script of
his own: the release program gained exactly the planned rows at their planned paths, none stayed
at the root, no other type changed, and the prototype's list did not change. Saved and confirmed
after each batch. Record: `docs/release/ghidra-types.tsv`, 284 rows.

What they unlock is planned next and not applied yet: the review's condition is that every
function they unlock is checked against its callers first, because these classes have no debug
record that could show a hidden argument.

## The signatures the placeholder types unlocked

With the 284 placeholder types present, a new whole-map plan (7f8bb7d8...) planned 804 more
entries of the group `mangled`. The review had set a condition for them: these receivers have no
debug record, so the rule that withholds a class-returning function from DWARF can never fire,
and every one has to be cleared against its callers and its own code first.

The reviewer built two checks for that and calibrated them on the ten known structure returns,
which they all flag. A function is cleared when it is a constructor or destructor (215), when on
some path its first access through a0 is a load, since a return buffer is written before it is
read (331), when a0 is never accessed, handed on or saved (169), when a caller sets exactly the
predicted argument registers (39), when a signed override of the same slot exists, a0 goes on to
a member that takes `this`, or every function a0 is handed to reads through it first (18), and by
hand for the rest (32, each with its reason in the reviewer's scratch). No caller sets a register
beyond the predicted ones. Result: all 804 cleared, none withheld; the 61 applied before pass
the same checks.

Applied in five batches (25, 100, 200, 250, 229), a snapshot after every ten writes, each checked
with the reviewer's script before its save: 804 prototypes and 804 plates, no stop, no change a
run did not make. The record holds 5,585 prototypes: 2,634 carried on exact pairs, 2,086 on
deviating pairs, 865 derived from the mangled symbol. Dry runs of the plan for all three groups
and of a names plan made afterwards send nothing.

Of the 6,991 functions of the game and engine modules 5,075 have a signature now, 852 of them
derived; `gamez/zUI` went from 107 to 379 of its 530, `gamez/zSeal` to 1,032 of 1,361,
`gamez/zNetwork` to 196 of 306. A receiver that is a placeholder shows its class name and raw
offsets, not members: the type has no layout yet.

Still without a signature in the group: 2,035 functions without a mangled symbol (C names, most
of them library code), 692 whose receiver and 498 whose parameter type cannot be named (template
names the endpoint's parser cannot read, types passed by value, names that are not C
identifiers), 199 with `this` undecided, 132 with a possible hidden argument.
