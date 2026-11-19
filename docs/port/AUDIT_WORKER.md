# Audit worker brief

You judge one list of the correctness audit ([AUDIT_PLAN.md](AUDIT_PLAN.md)). Read
[WORKER_BRIEF.md](WORKER_BRIEF.md) first; it applies in full. This file adds what is specific to
an audit list. Your prompt names the list, your scratch folder and the files you own.

## What you are given

- The list: `build/port/audit/<list>.md` (rows `| # | Address | Bytes | Symbol | File |`).
- One packet per function: `build/port/audit/packets/<list>/<row>-<address>.md`, with an
  `INDEX.md`; for a small-band list, one packet per source file (`f<n>-<file>.md`) holding all of
  that file's listed functions, with the facts they share once at the top (a file of more than 40
  functions keeps those facts and its contents table in `f<n>-<file>.md` and the functions in
  `f<n>-<file>.part<k>.md`). A packet holds:
  - the annotated ELF disassembly with the address first on every line: cite addresses from it,
    do not count lines (dropped save-register lines and nops outside delay slots leave a gap in
    the addresses). A label on every branch target, `| ` before a delay slot and `| nop` for a nop
    in one, calls demangled, data names demangled, a `lui` reaching its use through a delay slot
    followed along the branches, float words (`= 0.5f` a literal, `init` a variable), strings (also
    of 0 or 1 characters), data words (`= word` for a literal, `init` for a variable's initial
    value, `init 0` for a function's static), small literal objects such as pointer-to-member
    constants by their words, and jump tables resolved;
  - the port's own definition with file and line numbers, found by the fence's demangled name:
    lines between the fence and the definition (helpers, a `namespace {`) are skipped and named;
  - the bodies of the helpers it calls: same-file static, unnamed-namespace, inline and unfenced
    functions, the receiver class's header definitions, a `Base::Name()` call's definition, a short
    header definition when it is the only one of its name (also `obj->Inline()`), a port helper in
    another file that the ELF never calls (it inlined it), and the callees of a helper of six
    lines or fewer (60 lines each, 250 a packet, 400 a file packet);
  - the enumerators the body and its helpers name (also `Enum::NAME` of an enum class and a nested
    enum through its class) and every value of an enum whose type the body or signature names: the
    DWARF value and byte size, the port header's value when it differs, or the header's alone,
    marked, when DWARF has no such enum;
  - the vtable slot of each virtual call, resolved when the object's register is typed, else the
    methods at that slot the body calls;
  - members touched: DWARF names, a bitfield by name and bit within the byte, half or word the
    instruction accesses (narrowed by the mask the code applies), through a register that holds
    the receiver, a pointer-to-class argument, a call's result or a pointer member loaded from a
    typed object (`Class::member` then); `[port ...]` where the port's own layout (the comparison
    build) has no member of that name or puts the bitfield elsewhere, `port:` for a class DWARF
    lacks; other offsets by number;
  - the return value, when the port's definition is void (or float where the ELF uses v0, or the
    reverse) and the ELF writes v0 / `$f0` before returning or a caller reads it: each reading
    caller on one line;
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

- Helpers past the second level, the rest of a helper cut at 60 lines (or at the packet's cap,
  which the packet names), a helper whose name has several definitions none of whose classes the
  body names: the source.
- Callees that are ELF functions of their own, when their exact compare form matters: their
  packet, or the reference disassembly.
- Layouts of objects reached through an untyped register (a pointer read from an array, a cast
  the packet cannot follow): `mem.py <Class> <offset>` (bit positions included) or `dw.py`; enum
  values the body computes from others: the headers.
- The vtable slot of a virtual call through an object whose type the packet does not know, when no
  method at that slot is named in the body: `vt.py`.
- Run-time values of data: a packet shows only a variable's initial word.
- Register types are followed in listing order, not along branches (the lui values of the
  annotations and of the scan are merged along them). A member name can still be wrong after
  a branch join or at the vtable's offset (no DWARF member), and a `port:` name comes from the
  port's layout, which can sit at other offsets than the ELF's: trust the offsets. The
  disassembly is cut from the cached copy of the whole reference disassembly
  (`build/port/boot-auditkit/ref.dis`): run `dis.sh` on the range when something looks missing.

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

## Small functions from a by-file packet

The small band (functions under 200 bytes) comes as one packet per source file. Work file by
file in the scan's rank order of its highest-ranked function:

1. Read the file packet's top once: the contents table (its Notes column flags a return value
   that differs, virtual calls, a jump table, leads), the leads, helpers, enums, the members the
   file's functions touch, and the declarations. These hold for every function below them.
2. Then take the functions one by one (in a part file when the file has more than 40): the
   header line, the port source, its own notes (untyped offsets, return value, virtual calls)
   and the listing. Most are getters, setters, forwarders and flag tests: compare the offsets and
   widths (`lb` / `lbu`, a bitfield's bit), the constants, the call and its arguments, and what is
   returned (v0 / `$f0`, a `bool` as one byte) against the body.
3. Write one row per function as soon as it is judged, one line each: what was compared in a
   few words (`+0x1c m_count lw, returned`; `bit 3 of +0xdd set, others kept`). Cite addresses
   from the listing. A function the scan reports nothing for still gets its row.

Leave a function UNJUDGED (with the reason) rather than guess when the packet lacks what decides
it and the lookup tools do not settle it quickly; say what was missing in the note.

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
