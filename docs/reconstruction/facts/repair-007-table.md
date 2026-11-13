# Recon repair 007: withdraw unproven uchar returns (CNetCnf ticks)

Item `socom:work:recon-repair-007` corrects group `7ab334be`. It follows the user decision of 2026-10-24: an unproven sub-word or bool return becomes a partial row, `withdraws_return`, with the parameters exactly as live. Reviewer socom-verifier-r65 raised the finding. The precedent is group 280, which planned DeleteAllTick, SaveComboTick, SaveIFCTick and SaveDevTick partial.

| Address | Function | Live signature | Proposed signature | Evidence |
| --- | --- | --- | --- | --- |
| 0x3fe4e0 | CNetCnf::AddDevTick | `uchar __stdcall CNetCnf::AddDevTick(void * handle)` | `undefined __stdcall CNetCnf::AddDevTick(void * handle)` | Single exit `lbu v0,-32276(at)` = handle+0x81ec (0x3fe604), a byte of the untyped `void *` handle. The function does no narrowing of its own. Only the caller narrows (`andi s0,v0,0xff` at 0x1d1aa8, UINetAddDev), which proves only that caller's destination. |
| 0x3fe7a0 | CNetCnf::ReadInterfaceListTick | `uchar __stdcall CNetCnf::ReadInterfaceListTick(void * handle)` | `undefined __stdcall CNetCnf::ReadInterfaceListTick(void * handle)` | Single exit `lbu v0,-32340(at)` = handle+0x81ac (0x3fe8c4), a byte of the untyped handle. Only the caller narrows (`andi s5,v0,0xff` at 0x1d1b78, UINetGetInterfaceList), which proves only its destination. |
| 0x3ff920 | CNetCnf::OpenTick | `uchar __stdcall CNetCnf::OpenTick(void * handle)` | `undefined __stdcall CNetCnf::OpenTick(void * handle)` | Both exits `lbu v0,44(s0)` = handle+0x2c (0x3ff9c4, 0x3ff9d4), a byte of the untyped handle, not a typed member. Only the caller narrows (`andi v0,v0,0xff` at 0x1d2090, UINetCnfOpen), which proves only its destination. |

Checks run for all three functions:

- `recon facts --callers 99` shows one call site each, with no tail calls, no address-taken site and no table site, so `table-family` does not apply.
- `recon dwarf --address` and `--name` (plain and mangled) find no DWARF entry.
- `recon live --item` shows the live signatures above.
- `recon validate` passes (plan sha256 `acf8c7ee…0a0a`).
- `recon program` builds the program (sha256 `ea12fa94…6922`, 3 partial prototypes marked `withdraws_return`).
- `ghidra preflight-batch` passes (3 `set_function_prototype` calls, no errors).

The handoff has not been done.
