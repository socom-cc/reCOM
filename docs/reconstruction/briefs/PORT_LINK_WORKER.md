# Port lane - P1 link worker brief

Placeholders: `<repo>` is the repository root as the Linux side sees it (for WSL, the
`/mnt/...` form of the checkout), `<distro>` the WSL distribution (`SOCOM_WSL_DISTRO`),
`<user>` the Linux account.

You are a socom-source-worker on the functional port lane (AGENTS.md "Functional port lane";
build/port/PROPOSAL.md). P1 compile is done: every src/ header and unit compiles. Goal now: the
port ELF links. Everything in build/batch-helpers/PORT_COMPILE_WORKER.md still applies (scope by
folder, evidence order, fences and annotation blocks untouched, `/* port: unproven */` on guesses,
no shims in src/, Ghidra read-only with program=socom.elf, never commit) - read it first.

## Tools
- Link (PowerShell): `wsl.exe -d <distro> -- env SOCOM_PORT_BUILD=$HOME/.cache/socom/<you>-build bash <repo>/port/tools/link.sh`
  Prints library errors / failing units, then undefined and multiple-definition counts. Results in
  `\\wsl.localhost\<distro>\home\<user>\.cache\socom\<you>-build\` (`lib.log`, `link.log`,
  `undefined.txt` demangled, `multiple.txt`). The library must build before the link runs, so the
  whole tree has to compile: if another folder breaks the library, wait and retry; don't edit it.
- Sweep for quick per-file checks: `port/tools/sweep.sh units <filter>` (now includes holding files).
- `build/port/elf-demangled.json` (every ELF symbol, MW-mangled -> rendered declaration);
  `python tools/socom.py source sql "<SELECT>"` over the source graph: table `artifacts`
  (name = MW-mangled, inline, weak, classification authored/provider, library, tu, item) and the
  `@socom-artifact defines|emits` annotations in src/ name each function's owner file/header.
- `build/port/link-undefined-classified.json`: the parent's first classification of the 375
  undefined symbols (rough; re-derive from your own link).

## What changed for P1-link
- The port now BUILDS `*_holding.cpp` files (port lane only; the matching lane never does). They
  hold provisional code for functions stage 4 left without an owning unit. Your folders' holding
  files must compile like any unit (29 of 31 fail today). If a holding-file function duplicates a
  definition in an owned unit, the owned unit wins: put the holding copy under `#if 0` with a
  `/* port: duplicate of <file> */` note, don't delete it.

## Fixing undefined symbols (only those declared in your folders)
1. Signature mismatch (same name defined with other parameters/cv): the ELF's MW-mangled name is
   the identity. Make the declaration and the definition both match it; then fix callers minimally.
2. In the ELF, no definition in src/:
   - inline member emitted from a header (`artifacts.inline = 1`, header has `emits`): give it an
     in-class body in that header's class declaration (empty `{}` stub; non-void returns a neutral
     value only if you add `/* port: stub */`);
   - otherwise: add a stub definition (empty body) in its owner file per the `defines` annotation,
     or for an artifact with no owner (stage-4 deferred), in your module's `*_holding.cpp`, inside
     a `/* @socom-skeleton stub <mangled> */` fence like the others.
3. Not in the ELF at all: a provisional declaration. If callers in existing bodies use it, the
   original most likely inlined it (zMath helpers, VU0 macros): add an inline definition in the
   header when the behaviour is clear from evidence (assembly at a call site), else an inline stub
   flagged `/* port: unproven */`. If nothing should call it, remove the declaration and fix the
   caller from the assembly.
4. Provider symbols (Sony SDK, Medius, libptt, speech, 989snd, MSL, MW runtime): don't define them
   in src/. List them in your report; the parent implements them in port/compat.
5. Multiple definitions in your folders: keep the one that matches the ELF owner.

## Done and report
Done = no undefined or multiple-definition symbol whose declaration lives in your folders (other
than provider symbols you listed), and your holding files compile. Report <= 25 lines: per
category counts fixed; stubs added (where); inline bodies written from evidence vs flagged stubs;
provider symbols needed (mangled + demangled); cross-folder requests.
