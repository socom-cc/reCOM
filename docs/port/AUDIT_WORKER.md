# Audit worker brief

You judge one list of the correctness audit ([AUDIT_PLAN.md](AUDIT_PLAN.md)). Read
[WORKER_BRIEF.md](WORKER_BRIEF.md) first; it applies in full. This file adds what is specific to
an audit list. Your prompt names the list, your scratch folder and the files you own.

## What you are given

- The list: `build/port/audit/<list>.md` (rows `| # | Address | Bytes | Symbol | File |`).
- One packet per function: `build/port/audit/packets/<list>/<row>-<address>.md`, with an
  `INDEX.md`; for a small-band list, one packet per source file (`f<n>-<file>.md`) holding all of
  that file's listed functions, with the facts they share once at the top. A packet holds:
  - the annotated ELF disassembly: a label on every branch target, `| ` before a delay slot and
    `| nop` for a nop in one, calls demangled, float words, strings (also of 0 or 1 characters),
    data words (`= word` for a literal, `init` for a variable's nonzero initial value) and jump
    tables resolved;
  - the port's own definition with file and line numbers, found by the fence's demangled name:
    lines between the fence and the definition (helpers, a `namespace {`) are skipped and named;
  - the bodies of the helpers it calls, one level deep: same-file static, unnamed-namespace,
    inline and unfenced functions, the receiver class's header definitions, and a short header
    definition when it is the only one of its name (60 lines each, 250 a packet);
  - the DWARF values of the enumerators the body and its helpers name;
  - the vtable slot of each virtual call, resolved when the object's register is typed, else the
    methods at that slot the body calls;
  - members touched, named only through a register that still holds the receiver or a
    pointer-to-class argument; other offsets by number;
  - the receiver's member lines and the callee declarations it uses, the ELF callers and the leads
    earlier notes recorded.
  Functions over 3,000 bytes have their disassembly split into `.partN.md` files. Read the packet;
  do not fetch the same facts again with the tools. Fetch only what a packet lacks (see below), and
  say in your note what was missing so the packet tool can be fixed.
- The scan: `build/port/audit/scan-<list>.md`, the mechanical comparison of each function with
  the port's compiled code, ranked. A reported difference is a place to look, not a verdict: it
  flags two thirds of correct functions too, and it cannot see guards the ELF lacks, the order
  of float operations, or call arguments. A function with no reported difference still gets the
  full comparison.

## Known noise in the scan, and gaps in the packets

Learned from the lists already done. None of the scan items below is a defect by itself:

- The comparison build has inlining off, so a call to a small inline function the ELF inlined
  shows as "ELF never, port N times"; a port helper called in a loop where the ELF repeats the
  code inline shows as a call-count difference.
- GCC puts the vtable pointer first where the ELF's layout differs, which shows as offset
  differences; port layouts that differ from DWARF but are self-consistent do the same.
- Strings the linker merged as suffixes, and path strings of the comparison tree, show as
  missing or port-only.

What a packet may lack, and where to get it:

- Helpers past the first level, the rest of a helper cut at 60 lines (or at the packet's cap, which
  the packet names), a helper called through another object (`obj->Inline()`) or whose name has
  several header definitions: the source.
- Callees that are ELF functions of their own, when their exact compare form matters: their
  packet, or the reference disassembly.
- Bitfield positions and layouts: the headers (`dw.py`, `off.py`); enumerators of port-only enums
  and enum values the body computes: the headers.
- The vtable slot of a virtual call through an object whose type the packet does not know, when no
  method at that slot is named in the body: `vt.py`.
- Run-time values of data: a packet shows only a variable's initial word.
- Register types are followed in listing order, not along branches, and the vtable pointer has no
  DWARF member: a member name can still be wrong after a branch join or at the vtable's offset, so
  trust the offsets. The disassembly is cut from the cached copy of the whole reference
  disassembly (`build/port/boot-auditkit/ref.dis`): run `dis.sh` on the range when something looks
  missing.

Working habits that cost other workers time:

- From PowerShell, dot-source the user-local environment file your prompt names before every
  `wsl.ps1` call, and pass a flag separator as a quoted `'--'`.
- Do not rejoin lines with `fixnl.py` and do not run `sed -i` from Git Bash on a CRLF file (it
  turns the file to LF): check with `git ls-files --eol` and read your final `git diff`.
- When you redirect a script's output to a file, do not give it the name of one of the
  emulator's own logs (`gate-<check>.log`, `<run>.log`).
- Float compares are written as the ELF has them, including a form that differs only for a NaN
  (a `>` where the ELF tests not-less-or-equal): grade those C.
- For functions under about 700 bytes, work file by file within the scan's rank order: take the
  highest-ranked function, then judge the rest of that file's functions while its helpers,
  layouts and enums are in your head, and write that file's rows in one go.

## What you do

1. Work in the scan's rank order, highest score first, so the likeliest defects are judged
   before a usage limit can stop you.
2. For each function compare the port's body with the ELF instruction by instruction, as
   AUDIT_PLAN.md "What correct means" says: operand order, widths and signedness, the order of
   float operations, constants' words, calls and their arguments (registers and stack), what is
   stored where and when, and guards the ELF does not have.
3. Verdict per function: `MATCH`; `DEFECT-FIXED` graded A (changes what the player sees, or
   crashes), B (wrong, masked on this disc) or C (cosmetic); `DEVIATION-KEPT` only with the
   reason recorded in the code; `UNJUDGED` with the reason. Fix defects in place, from the ELF.
   ELF quirks are kept and noted. Nothing is tuned and no guard is added.
4. After each function, append its row to your note and to `NOTES.md` in your scratch folder, so
   nothing is lost if you are cut off. Do not batch the writing to the end.

## Testing, in proportion

- No emulator run per function. A targeted trace only for a grade A or B fix that the demo
  mission can reach, several fixes per run.
- One smoke run at the end, by kind of change (WORKER_BRIEF.md "Testing"). The coordinator runs
  the full behaviour check on the merged commit.
- The default build must link on your final tree.

## The note

`docs/port/notes/audit-<list>.md`, part of your `mine.txt`. Keep the first column layout exactly,
because `auditlist.py` reads judged addresses from it:

```
| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
```

Above the table: counts by verdict and grade, the defect rate, the fixes in one line each with
the ELF address that justifies them, the kept deviations, leads for other lists, what the packets
lacked, and the runs. It must pass `python tools/socom.py audit independence --strict`.

## Final report

At most 12 lines: counts, the A and B fixes, kept deviations, runs, files changed (= `mine.txt`),
edit files for files you do not own, open questions, and how many rows are left if you stopped
early.
