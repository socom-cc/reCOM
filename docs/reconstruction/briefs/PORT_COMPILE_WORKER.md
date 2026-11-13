# Port lane - P1 compile worker brief

Placeholders: `<repo>` is the repository root as the Linux side sees it (for WSL, the
`/mnt/...` form of the checkout), `<distro>` the WSL distribution (`SOCOM_WSL_DISTRO`),
`<user>` the Linux account.

You are a socom-source-worker on the functional port lane (AGENTS.md "Functional port lane", read
it first; build/port/PROPOSAL.md is the plan). Goal of P1: every `src/` header compiles on its own
and every `src/` unit (except `*_holding.cpp`, never built) compiles with the pinned ps2dev GCC.
Function bodies are NOT written in P1: empty stub bodies stay empty.

## Your scope
You own only the module folders named in your prompt (headers and .cpp). Edit nothing else in
`src/`. If a fix belongs in another worker's folder, do not make it: list it in your report
(file, line, the change, evidence) and work around it only by waiting and re-sweeping. Shared,
append-only exception: SDK compatibility headers under `port/compat/include/` (see below).

## Tools
- Sweep (run from PowerShell; Git-Bash mangles /mnt paths):
  `wsl.exe -d <distro> -- env SOCOM_PORT_SWEEP=$HOME/.cache/socom/<you> bash <repo>/port/tools/sweep.sh headers <filter>`
  and `... sweep.sh units <filter>`. The filter is a grep pattern on the path (e.g. `zAI/`).
  Logs: `\\wsl.localhost\<distro>\home\<user>\.cache\socom\<you>\<mode>\log\<path_with_underscores>.log`.
  Use your own SOCOM_PORT_SWEEP directory, never the default.
- Forced prefix `port/include/socom_port_prefix.h` (owned by the parent; ask in the report).
- DWARF, primary evidence: `build/port/dwarf-graph-rows.json` (types with members, bases, sizes;
  879 functions with return types; MW DWARF 1 encodes bool as fund_type 3 = unsigned char) and
  `build/port/dwarf-rows.json`. Template instances are named just `vector`/`list`; their
  `std::__vector_imp<T,...>` / `__list_imp` bases give the arguments.
- Ghidra is live and read-only for you: run `python tools/socom.py ghidra preflight --strict` once,
  pass `program=socom.elf` on every call, never write/save/open/switch/run scripts.
- `python tools/socom.py reference demangle <mangled>` for parameter lists of skeleton stubs.

## How to fix
- Evidence order (AGENTS.md): assembly/xrefs, DWARF and symbols, Ghidra, then guesses. C++ rules
  are evidence too (an override returns its base's type; a base class must be complete).
- Typical fixes: missing `#include` of the header that defines a base class or by-value member;
  forward declarations (`class X;` in the right namespace) for pointer/reference uses; missing
  standard headers (`<vector>`, `<list>` ...); nested types or enums referenced but never declared
  (take enumerators from DWARF; if unknown, declare the type with a `/* port: unproven */`
  comment); mismatched declaration vs definition signatures (match the mangled name in the
  `@socom-skeleton stub <mangled>` fence - it is the binary's identity, it wins).
- Keep `socom-owner-annotations` blocks byte-identical and every `@socom-skeleton` fence comment
  line in place. Edit declarations inside `decl ... end` regions freely.
- Every guess carries `/* port: unproven */` (or a short reason). No `#ifdef SOCOM_PORT` unless
  one spelling can't serve both compilers; say why in the comment.
- Never add shims, fake providers or stub implementations of SDK/library functions in `src/`
  (`guard provider` rejects them). SDK (Sony `sce*`, libgraph, libdma, eekernel...) or other
  provider *declarations* that src code needs go in `port/compat/include/<original header name>`
  (e.g. `eekernel.h`, `libgraph.h`, `sifdev.h`); src includes them with `<...>` as the original
  source would. These compat headers are shared: re-read before every edit, append declarations
  with the Edit tool, never rewrite or reorder others' lines, guard each header. Prototypes come
  from the call sites' evidence (Ghidra/assembly); flag guesses.
- GCC differences to respect: `long` is 32-bit here but 64-bit on Metrowerks PS2 - if DWARF says a
  type is 8 bytes, use `s64/u64`, never `long`. 128-bit values use
  `unsigned int __attribute__((mode(TI)))` (add a `u128`-style typedef to the prefix via your
  report, don't invent per-file ones).
- No behaviour changes in existing (non-stub) bodies beyond what compiling requires; if a body is
  wrong for GCC, fix minimally and note it.

## Done and report
Done = your folders' headers and units all compile (or the remaining failures are blocked on
another folder or the prefix, listed). Don't commit. Report <= 25 lines: per folder headers/units
ok/total before -> after; edits by kind with counts; every `port: unproven` guess count; cross-folder
requests; compat headers you created/extended.
