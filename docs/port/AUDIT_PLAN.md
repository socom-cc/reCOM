# Correctness audit of every module: plan

The port's game code is complete (no empty function is left), but most of it was written once and
shown working only where the demo disc exercises it. The audit compares every function with the
reference ELF and fixes what differs. This file is the plan; results go to
`docs/port/notes/audit-<list>.md`, one note per list.

## What "correct" means

- The standard is the reference ELF's behaviour, read from its disassembly, instruction by
  instruction: operand order, widths, signedness, the order of float operations, the constants'
  words, calls and their arguments (registers and stack), what is stored where and when.
- Verdict per function, as in the finished zSeal / zAI audit:
  - `MATCH`;
  - `DEFECT-FIXED`, graded A (changes what the player sees, or crashes), B (wrong, but masked on
    this disc), C (cosmetic: rounding order, a guard the ELF does not have, an unread value);
  - `DEVIATION-KEPT`, only with the reason recorded in the code;
  - `UNJUDGED`, with the reason. A list is not done while it has one.
- The ELF's own oddities are kept and noted as quirks. Nothing is tuned and no guard is added.
- Every list also checks, for the functions it judges: three-term float sums in the ELF's order,
  arguments passed on the stack, inexact float literals read back from the object
  (`docs/port/notes/float-constants.md`), and constants the ELF computes at startup with its own
  math routines (the `KNIFE_DOT` case in `audit-large-a.md`).

## Where it stands

Fenced functions: 4,845 (1.93 MB). Judged so far: the 248 functions of 700 bytes or more in zSeal
and zAI (63 defects: A 3, B 14, C 46), a random sample of 5.8% of the rest, and the functions
without a fence (508). Still to judge, from `port/tools/dev/auditlist.py --summary`:

| Band | Functions | Bytes |
|---|---|---|
| large: 700 bytes or more | 398 | 629 KB |
| medium: 200 to 699 | 1,707 | 633 KB |
| small: under 200 | 2,372 | 199 KB |

The defect rate found so far falls with size: about one large function in four, about one in
seventeen in the mixed-size sample. So the large band goes first.

## Phase 1: large functions (13 lists, 5 rounds of three workers)

One list is about 50 KB of functions, which is what one worker judges in one session. Lists hold
whole files, so no two workers edit the same file. Order: what the player sees and touches most
first; modules another task is working in wait for that task.

| Round | List | Modules | Functions | KB |
|---|---|---|---|---|
| 1 | hud-a, hud-b | Apps/FTS/hud | 83 | 123 |
| 1 | anim-a | zAnim (first third) | 20 | 48 |
| 2 | anim-b, anim-c | zAnim (rest) | 40 | 97 |
| 2 | ui-a | zUI (first half) | 24 | 37 |
| 3 | ui-b | zUI (rest) | 24 | 37 |
| 3 | fts | zFTS | 26 | 33 |
| 3 | apps | Apps/FTS game, state, top level | 32 | 49 |
| 4 | world | zNode, zGrid, zVisual | 32 | 48 |
| 4 | draw | zCamera, zParticle, zTwoD, zRender | 35 | 57 |
| 4 | combat | zWeapon, zNetwork, zVehicle, zCharacter | 40 | 48 |
| 5 | rest | the nineteen small modules | 39 | 43 |

zNetwork is judged against the ELF like the rest; it cannot be run on this disc, so its fixes are
read-only evidence until the later stage that tests online play.

## Phase 2: medium functions (about 13 lists, 5 rounds)

Same method and the same module order, with zSeal (391 functions, 148 KB) and zAI (87, 31 KB)
added, since only their large functions were judged. A list is again about 50 KB, which is about
130 functions here.

## Phase 3: small functions (about 8 lists, 3 rounds)

2,372 functions under 200 bytes: accessors, forwarding calls, small constructors and destructors.
They are judged in bulk: a list of about 300, each compared with its ELF body, the verdict table
kept as short as one line per function. A defect here is usually a wrong member, a wrong constant
or a missing store.

## How a round runs

1. The coordinator makes the lists: `python port/tools/dev/auditlist.py --band large --modules
   <regex> --split <n> --out <name>` (functions a note already lists are left out).
2. At most three workers, one list each (`docs/port/WORKER_BRIEF.md`). Each judges its list in
   size order, largest first, fixes defects in place, and writes its note with the verdict table.
   Testing per the brief: a targeted trace where the disc can reach the changed code, and one
   smoke run.
3. The coordinator merges each list as one commit, runs the audits (`audit docblocks`,
   `guard provider`, `audit independence --strict`, `audit docs --strict`) and the full
   behaviour check (`port/tools/dev/gate.ps1`) on the merged commit.
4. A list that stops unfinished is continued by a follow-up worker from its note and its scratch
   folder; the rows already judged are not repeated.

About 13 + 13 + 8 = 34 lists in 13 rounds. The pace is set by the usage limit, not by the
machine: a round is three worker sessions plus the merge and the checks.

## What the audit does not cover

- Whether the port's compiler makes the same code: it cannot (GCC, not Metrowerks); the build
  flags in `port/CMakeLists.txt` remove the assumptions GCC makes that the original compiler did
  not.
- Behaviour that needs data or services this disc does not have (the other missions, ladders,
  online play, voice): judged against the ELF, not run.
- Functions without a fence whose owner or place is still being decided: they were judged in
  `audit-unmarked-*.md` and move with their owner.
