# Stage 3 local-variable typing — design (not implemented)

Scope: the approved zAnim plan. Each zAnim callback receives `_zanim_cmd_hdr *` and casts it to a
command record (DWARF zcam_main.cpp: `cmd` / `cmd_ptr` typed `_camera_params_cmd *` etc.). Once the
record types exist, each callback's cast local should carry its record type so decompilation reads
`cmd->field`.

Read-only investigation (2026-10-23). Endpoint semantics come from:

- the installed plugin's bytecode (`javap -c -p` on
  `%APPDATA%\ghidra\ghidra_12.1.4_PUBLIC\Extensions\GhidraMCP\lib\GhidraMCP-6.0.0.jar`, classes
  `FunctionService`, `EndpointRegistry`, `AnalysisService`, `XrefCallGraphService`, `ServiceUtils`,
  `SwingThreadingStrategy`);
- the Ghidra 12.1.4 sources shipped with the install
  (`Ghidra\Framework\SoftwareModeling\lib\SoftwareModeling-src.zip`: `HighFunctionDBUtil`,
  `LocalSymbolMap`, `HighVariable`, `HighSymbol`, `SymbolEntry`).

Live probes were GET only, on 0x1ba280 and 0x1e7320 (`get_function_by_address`, `decompile_function`,
`get_function_variables`, `analyze_for_documentation`). They ran while
`recon-repair-003-apply` held the writer lease. No writes, tracker mutations or commits.

## 0. Verdict

| Callback shape (zanim-scan `cb_asm.txt`, 224 functions) | Count | Can the cast local be typed with GhidraMCP 6.0.0? |
| --- | --- | --- |
| parser, calloc result kept in an s-register (`move sN,v0`) | 75 | **Yes.** A separate HighSymbol exists (probe: `p_Var1`, representative v0, typed `_zanim_cmd_hdr *` by return propagation). |
| parser, result stays in v0 / other | 22 | Yes when a separate HighSymbol exists (resolved per function). Header-only records need no new type. |
| begin/tick/end, `move sN,a0` copy | 76 | **No.** The decompiler merges the copy into the parameter (probe 0x1ba280: only `param_1` and `pCVar1`). No endpoint creates or splits a local. |
| begin/tick/end, record reached through a0 only (leaf, or calls without a copy) | 51 | **No, structurally.** There is no defining op to bind a local to. Only a parameter retype would show fields, and that contradicts the mangled `P14__zanim_cmd_hdr` and the DWARF `hdr` contract. |

So the step is feasible now for the ~97 parsers. For the 127 begin/tick/end callbacks it needs a user
decision; §4 R4 lists the options.

## 1. Bridge endpoints that set local types or names

All variable writes end in Ghidra's `HighFunctionDBUtil.updateDBVariable(sym, name, dt, USER_DEFINED)`.
They differ in how they find the symbol and whether they commit parameters.

| Endpoint (HTTP) | Identifies by | What it does | Parameter / prototype side effects |
| --- | --- | --- | --- |
| `set_local_variable_type` (POST `function_address`, `variable_name`, `new_type`) | Exact **decompiler** name: the first HighSymbol in `LocalSymbolMap.getSymbols()`, **parameters included**. | Rejects `undefined*` types. Runs `decompileFunctionWithRetry` (flushCache), resolves `new_type` (`ServiceUtils.resolveDataType`: well-known table, then `/name`, then lower-case, then first match in any category, then `[n]`), then in its own transaction "Set variable type" calls `updateDBVariable(sym, sym.getName(), dt, USER_DEFINED)`. | **Local:** no parameter commit. **Parameter name:** `getDatabaseParameter`. If the DB parameter slot or storage differs from the decompiler's, it calls `commitParamsToDatabase(hf, useDataTypes=true, NO_COMMIT, ANALYSIS)`, which rewrites the whole parameter list, and then sets that parameter's type. |
| `set_decompiler_variable_type`, `set_parameter_type` | Same | Literal aliases: name `this` goes to `set_function_this_type`; any other name goes to `setLocalVariableType`. | Same as above |
| `set_variables` (POST `function_address`, `variables` JSON `{old: {name?, type?}}`) | Phase 1 (types): **listing (DB) variables only**, matched by name via `getLocalVariables()` then `getParameters()`. A decompiler-only local "is not found" and fails. | One transaction "Set Variables" on the Swing thread. Phase 1 is `Variable.setDataType(dt, USER_DEFINED)`. Phase 2 **always** decompiles. If `checkFullCommit(first HighSymbol iterated)` is true, it runs `commitParamsToDatabase(hf, false, NO_COMMIT, signatureSource)`, **even for a type-only payload**. Renames go through `updateDBVariable(sym, newName, null)`. | Can rewrite the prototype, depending on HashMap iteration order. **Do not use.** |
| `rename_variable` (POST `function_address`/`functionName`, `oldName`, `newName`) | Decompiler name (HighSymbol) | Decompiles, then `checkFullCommit(sym)`, then `executeWrite`: optional `commitParamsToDatabase(hf, false, NO_COMMIT, signatureSource)`, then `updateDBVariable(sym, newName, null)`. Hungarian prefix check gives **warnings only**. | Parameters only (`checkFullCommit` returns false for a local). A not-yet-committed local is committed as `undefined<n>`, which is not type-locked. So **retype first, rename second.** |
| `rename_variables` / `batch_rename_variables` | Decompiler name | Same as `rename_variable` per symbol (flushCache, decompile, `checkFullCommit`, `commitParamsToDatabase`, `updateDBVariable`), plus a listing `setName` fallback. | As `rename_variable` |
| `batch_rename_function_components` | Listing names | `Function.setName`, `Parameter.setName`, `Variable.setName` on DB locals, `setReturnType` | No decompile. Renames existing DB locals only. |
| `set_variable_storage` | n/a | **No-op.** Returns advisory text ("Programmatic variable storage control is limited…"). | None |

What `updateDBVariable` changes for a **local** (Ghidra 12.1.4 source):

- It writes the **listing variable** (`LocalVariableDB`), not a HighVariable.
- Storage is the HighSymbol's representative storage. If the representative is a temporary or a
  stack value that is not address-tied (`requiresDynamicStorage`), storage becomes **HASH** (dynamic)
  and the size may not change.
- First-use offset is `HighSymbol.getPCAddress() - entry`.
- `clearConflictingLocalVariables` first **removes** any DB local at the same first-use offset whose
  storage intersects but is not equal.
- If no local exists, `createLocalVariable` adds it **and adds a register WRITE reference at the
  first-use pc** (`addRegisterReference(pcAddr, -1, reg, WRITE, USER_DEFINED)`).
- The name is always written. With `set_local_variable_type` it is the current auto name (`p_Var1`)
  as USER_DEFINED.
- Merge sets (`name$1`…) are retyped together.
- `LocalSymbolMap.grabFromFunction` then name-locks every DB local, and type-locks it unless the type
  is `undefined`. The decompiler binds the DB local through a one-point range list `[pc, pc]`
  (`SymbolEntry.encodeRangelist`): exactly the varnode defined at the first-use pc. A v0 local does
  not capture later v0 values.

Persistence: the DB local (name, type, storage, first use, source) and its register reference are
ordinary program-DB records. They persist through the single `save_program` in
`progress handoff-live-ghidra`. Decompiler names of uncommitted symbols are transient and are
renumbered on each decompile; the plugin itself warns about "SSA-renumber drift".

**Recommended endpoint:** `set_local_variable_type`, one row per call, followed by `rename_variable`
when the row names the local. Do not use `set_variables`, `set_parameter_type` or
`set_decompiler_variable_type`.

## 2. Read-back and verification

### Read-only endpoints

| Endpoint | Read-only? (bytecode) | What it gives |
| --- | --- | --- |
| `get_function_variables` (GET `address`) | **Yes.** `executeRead` runs on the Swing EDT with **no transaction**; the decompile is used only for `is_phantom`. | DB parameters (`name`, `type`, `ordinal`, `storage` such as `a0_lo:4`) and DB locals (`name`, `type`, `storage`, `is_phantom`), limit 200. **No first-use offset. No category path.** Heuristic keys (`needs_*`, `suggested_*`). |
| `analyze_for_documentation` (GET `function_address`) | **Yes** (Swing `invokeAndWait`, no transaction) | All HighSymbols, parameters included, with `name`, `type` and representative `storage` as a raw varnode (`register:00000020:4` = v0, GPR n at offset 0x10·n; a0 = 0x40 cross-checks with parameter `a0_lo:4`), plus the C text. Used to **resolve** the target before a write. |
| `decompile_function` (GET) | **Yes** (fresh DecompInterface, no transaction, runs on the HTTP thread) | C text only: declared local names and types, field syntax. |
| `get_xrefs_from` (GET `address`) | Yes | `ReferenceManager.getReferencesFrom(pc)`, register references included: the **only first-use read-back** (the createLocalVariable reference). |

The earlier verifier and planner briefs banned `get_function_variables` and decompiles as a
precaution; the bytecode shows they cannot write. What they really cost is that each one decompiles
on the Swing thread and blocks the GUI and bridge. Keep them out of sweeps that run in parallel with
other bridge traffic. That cost, not mutation, is the real constraint.

### Current coverage: neither covers locals

- **`ghidra receipt`**: per scoped function it records `get_function_by_address` (Function, Signature,
  Entry and Body lines; `Function.getSignature()` covers parameters and return only) and
  `disassemble_function` (`Instruction.toString()` plus EOL comment, with no variable markup).
- **`ghidra fingerprint`**: the same function details for every function, plus references from a
  `get_bulk_xrefs` sweep of `getReferencesTo` over **memory** addresses. Register references target
  the register space and are invisible to it.
- Both **do** catch the dangerous side effect: an unintended parameter commit changes the
  `Signature:` line.

### Needed extension (additive; existing digests unchanged)

1. **Receipt scope key `variables`** (sorted function addresses). `normalize_receipt_scope` accepts
   it; when it is absent the receipt stays byte-identical to schema 1, so accepted items and
   in-flight handoffs keep their digests. When present, `scoped_facts.variables[]` records, per
   function:
   - `parameters` from `get_function_variables`: `[ordinal, name, type, storage]`;
   - `locals`: `[name, type, storage]`, with heuristic keys and `is_phantom` dropped;
   - `register_refs`: the register-space refs from `get_xrefs_from` over the function's
     `disassemble_function` addresses.

   Receipt `schema_version` becomes 2 only when the key is present.
   `progress record-stage-baseline` must union `variables`.
2. **Fingerprint: no change.** A local-typing apply must leave the fingerprint **identical**. Any diff
   (above all a `Signature:` line) is a defect.

## 3. ELF-side identity and plan-row targeting

- **Parsers.** `jal calloc` (zmalloc wrapper `_calloc(1, size, file, line)`) whose a1 equals the record
  size, the header store `sh` at `+2` of `(size<<2)|…`, the result in v0 at the jal pc, and copies
  `move sN,v0`. The decompiler's representative for the record local is **v0 at the call**
  (probe 0x1e7320: `p_Var1` `register:00000020:4`), not DWARF's `s0`.
- **DWARF register numbers are not storage evidence here.** Parameters are recorded in v0, and leaf
  locals (`cmd` in CmdTickControlSwitch) in v0, which the code never uses that way. Use them only for
  names and types.
- **Row identity**, stable across renumbering:
  `(function entry, anchor register set {v0@jal pc, sN@move pc…}, candidate def pcs from the ELF, expected pre-type)`.
  - Decompiler names are never stored in the plan. They are resolved at preflight and again
    immediately before the write, and must agree.
  - After the commit the binding is exact: DB local storage plus first-use pc, read back through the
    register reference, which must be one of the ELF candidate def pcs. The name is then locked.

Plan row (file-only, `build/local-plans/<slug>.json`):

```json
{
  "function": "0x1e7320",
  "current_name": "zdb::CCamera::CmdParseSetRegions",
  "live_signature": "_zanim_cmd_hdr * __stdcall zdb::CCamera::CmdParseSetRegions(_zrdr * rdr)",
  "role": "parser",
  "anchor": {"kind": "call-result", "call_pc": "0x1e736c", "callee": "_calloc", "size": 8,
             "registers": ["v0", "s0"], "def_pcs": ["0x1e736c", "0x1e7374"]},
  "expected_pre_type": "_zanim_cmd_hdr *",
  "type": "_camera_set_regions_cmd *",
  "name": "cmd",
  "evidence": {"record_type": "socom:work:type-plan-<...>-apply | dwarf 0xf2c50",
               "name": "dwarf local 0x... | convention", "data_size_store": "0x..."}
}
```

`call_pc` and `def_pcs` above are illustrative; the drafter derives them from the ELF. Rows that
cannot be typed go in `unresolved` with a reason such as `record pointer is the parameter (move s0,a0
merged)` or `a0-only leaf`. The plan has at most one row per (function, register).

## 4. Risks

- **R1. Decompiler-only target.** Before the commit the local exists only as a HighSymbol with a
  renumbered auto name. Each retype can rename other locals (`p_Var2` becomes `p_Var1`).
  Mitigation: resolve by storage plus pre-type plus "not a parameter" via `analyze_for_documentation`;
  handle one row at a time and re-resolve after every write; refuse ambiguous rows (two candidates in
  v0 is common: probe `p_Var1` and `p_Var2`).
- **R2. Parameter path.** `findSymbolByName` searches parameters too. A resolved name that is a
  parameter commits the whole prototype (`useDataTypes=true`, source ANALYSIS). Mitigation: refuse
  any name present in the parameter list; read back `Signature:` unchanged.
- **R3. Hidden side effects.** Each commit adds a register WRITE reference, may delete intersecting DB
  locals at the same first use, and makes the auto name USER_DEFINED. HASH storage is fragile (its
  hash depends on p-code). Mitigation: require DB locals to equal the recorded pre-state (probes:
  `total_locals` 0); refuse non-register storage; extend the receipt (§2).
- **R4. Merged or a0-only callbacks (127).** No bridge path; scripts are forbidden by AGENTS.md;
  retyping the parameter contradicts mangled and DWARF evidence. User options:
  - (a) A plugin capability (outside this repo) that adds a DB local by explicit storage and first-use
    pc (`Function.addLocalVariable(LocalVariableImpl(name, firstUse, dt, reg))`). The `[pc,pc]` binding
    would split the `move sN,a0` copy out of the parameter. Covers 76; the 51 a0-only callbacks stay
    impossible.
  - (b) Keep `hdr` and explain the offsets with EOL comments naming record and field (these are
    receipt-covered).
  - (c) Record the gap in TOOL_COVERAGE.md and the issue ledger.
- **R5. Later type and prototype changes.** A committed local refers to its record type by ID.
  - A later type-plan rename, replace or delete of the record silently changes the local (a delete
    leaves it undefined). `recon type-plan affected` and type applies must count locals as users.
  - `set_function_prototype` does not touch register locals with first use > 0. Even so, a recon
    repair of a typed function should re-run `check-locals`.
  - Locals do not propagate to callers.
- **R6. Interaction with group applies.**
  - Ordering: local typing runs only after the function's group or repair apply **and** the record
    type apply are accepted.
  - Single writer.
  - The fingerprint stays identical. Check `analysis_status` before and after: a reference-added event
    must not start auto-analysis.
  - EDT-blocking reads: do not run beside another apply. Watch timeouts on large functions
    (CmdParseParams is 3944 bytes).
- **R7. Type resolution.** The bridge resolves by bare name and `get_function_variables` reports only
  `DataType.getName()`. Require a name that resolves exactly once ignoring case and is not in the
  well-known table (reuse `batch_apply.ambiguous` and `_data_alias_problem`).
- **R8. Replay.** `ghidra restore-accepted` has no replay route for stage 3 kinds (an existing gap);
  this kind joins it.

## 5. Proposed commands and acceptance contract

Each command below is new; the list gives its mutation class and job.

1. `progress add-local-types --name <slug> --functions <hex…>`: tracker mutation.
   - Adds a file-only plan item (`recon-local-plan`, resources `build/local-plans`) and an apply item
     (`recon-local-apply`, `ghidra-writer`). Both join the stage 3 gate.
   - The plan depends on the accepted group or repair apply items of every function and on the
     accepted type apply of every record type. The apply depends on the plan.
2. `recon locals draft --item <plan>`: file-only. Derives rows and unresolved entries from the ELF:
   anchors, sizes, `def_pcs`, DWARF names, and record types from accepted type plans. `--check`
   re-derives the drafted rows.
3. `recon locals validate --plan`: file-only.
   - Anchors re-derive from the ELF; the size equals the record type size.
   - Types and functions are owned by accepted items; there are no duplicates.
   - `name` is a valid identifier or null.
4. `recon locals program --plan --output build/apply/<slug>-apply.json`: file-only and deterministic.
   Ops per row:
   `precheck {signature, db_locals_before, type_unique, no_reg_ref_at def_pcs}`, then
   `resolve {registers, pre_type, not_param}`, then
   `set_local_variable_type {function_address, variable_name:<resolved>, new_type}`, then optionally
   `rename_variable {function_address, oldName:<resolved>, newName}`, then `readback`.
5. `ghidra preflight-locals --program --output build/preflight-recon/<item>-claimed.json`:
   live and read-only. Runs every precheck and the resolution; records the resolved names and the
   would-be calls.
6. `ghidra apply-locals --item --owner --program [--dry-run]`: live write under the lease.
   - Repeats all prechecks before any write and requires each resolution to equal the claimed one.
   - Then per row: retype, re-resolve, rename.
   - Then read-back:
     - `get_function_variables`: parameters unchanged; locals = before plus exactly `{name, type,
       storage}`;
     - `Signature:` unchanged;
     - `get_xrefs_from`: one new register WRITE reference at one `def_pc`;
     - `decompile_function`: declares `<type> <name>` and uses `name->`.
   - Writes `build/apply/<item>-report.json` and the scope `{functions, variables}`.
7. `ghidra check-locals --item --accepter`: read-only verifier checklist (pattern of
   `check-recon-apply`). It checks:
   - plan and program sha256 cited in the evidence;
   - lease and item kind; strict preflight;
   - the receipt reproduces, variables included;
   - a fresh fingerprint equals the handoff's after-fingerprint, and before = after;
   - the apply calls equal the claimed dry run, using only the two endpoints;
   - per-row read-back; `progress audit --strict`.

Contract:

1. The applier claims the apply item.
2. The applier runs `preflight-locals`, then fingerprint before, `apply-locals`, and fingerprint
   after (which must be identical).
3. The applier runs `progress handoff-live-ghidra --scope build/receipts/<item>-scope.json`. It saves
   once, and the receipt, variables included, must be stable across the save.
4. A different owner runs `ghidra check-locals`, then `progress advance-live-ghidra`, which re-reads
   the stored scope and requires the same digest.
5. Pilot first: one parser apply item to measure the exact `storage` text of a DB local (expected
   `v0_lo:4`), the `get_xrefs_from` line for a register reference, and the analysis-idle behaviour.
   Freeze the read-back expectations only after that. This is the memory rule: verify by a probe
   before claiming.

## 6. Estimated tool work

About 1.3–1.5k lines of Python plus about 30 tests, over 2–3 maintainer sessions, plus one pilot:

| Part | Lines (approx.) |
| --- | --- |
| draft + validate + program | 450 |
| preflight + apply executor | 300 |
| check-locals | 200 |
| receipt `variables` scope (+ normalize, stage baseline, migration-free) | 150 |
| tracker add-local-types + packets | 120 |
| registry, generated docs, agent surfaces, TOOL_COVERAGE | small |

The 127 begin/tick/end callbacks stay blocked until the user picks an R4 option.
