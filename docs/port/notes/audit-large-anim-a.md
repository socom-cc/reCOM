# Audit of list large-anim-a (2026-11-16, socom-port-audit-anim-a)

The four largest zAnim functions, all in `gamez/zAnim/anim.cpp` (50,036 bytes). HEAD d17cfec1.
Judged in the scan's rank order (rows 1, 3, 4, 2), each over its whole address range.

Method: the two table-like functions (DefineFPAnims, 133 inlined steps; InitializeAnimNames, 157
inlined lookups) were read block by block and then compared mechanically: a script over the
packet disassembly extracted every step's operands (constants, AnimTypes:: statics, group field
offsets, the m_basetypes index and value, string addresses) and checked each block has the one
shape, then compared the list with the port's calls in order. The two loaders were compared
instruction by instruction by hand.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 4 |
| DEFECT-FIXED | 0 |
| DEVIATION-KEPT | 0 |
| UNJUDGED | 0 |

Defect rate 0 / 4. No fixes. No kept deviations.

ELF quirks kept: InitializeAnimNames gives MovingPistol2Rifle the "Moving rifle -> Pistol" string
and CQBVictimFallBackwards the "Death stand head01" string (both now commented in the code);
AnimSet::Load appends 143 more CAnimAuxData on every call without clearing the list;
Load(_zrdr*) reads motion.rdr anim index 0 as "none" (already commented).

Leads for other lists: none.

What the packets lacked: packet 1 (DefineFPAnims) showed only the helper `DefineFPAnim` that sits
under the stub marker, not the `AnimSet::DefineFPAnims` body after it (read from anim.cpp
1506-1653); the three `@2443/@2465` fill words and 0x475090..9c (the -1 pushed values) were read
from the ELF; the AnimSet and CAnimAuxData inline ctors and `_zrdr::Get` were read from the
headers. Otherwise sufficient.

Runs: none (comments only). The default build links (`default.sh`).

## Table

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 1 | 0x2c0970 | 29668 | AnimSet::DefineFPAnims() | gamez/zAnim/anim.cpp | MATCH | - | Whole range 0x2c0970-0x2c7d54 compared. Prologue: new(4), _malloc(2400, line 1351), Clear(), store to m_animgps (+0x60) even when new fails: same. 133 inlined steps extracted from the ELF by script (group stores rifle then field at 8*rifle+{2,4,6}, m_basetypes grown with -1 up to other, m_basetypes[other] = rifle; AnimId of both evaluated, both must be >= 0) and compared with the port's 133 DefineFPAnim calls in order: rifle, partner (constant or AnimTypes:: static) and field all equal. The three -1 fill words (0x47531c/20/24) are -1. ELF evaluates both AnimIds before testing; the port short-circuits (no side effect). zmalloc passes the port's own file/line (debug only). |
| 3 | 0x2cc3c0 | 1012 | AnimSet::Load() | gamez/zAnim/anim.cpp | MATCH | - | Whole range 0x2cc3c0-0x2cc7b4 compared: numAnimTypes = 143 before newNamesMap.clear(), loadCount++, reserve + 143 `new CAnimAuxData` (bit 0 cleared, the inline ctor), the name loop re-reading numAnimTypes, motion.rdr loop (i from 1, value i - 1, count re-read from array[0]), zrdr_free(motion) unguarded, list size zeroed, reserve(32) when capacity < 32, animset.rdr loop (&array[1] .. &array[count], static Load(_zrdr*)), read = 1 only when the file opened, animNamesMap.clear, InitializeAnimNames, DefineFPAnims per set, InitDeathAndFlinchAnimations, ReadDeathAndFlinchAnims when deathanim[0][0] is empty, include loop (strcmp with m_name +0x38, first match, Inherit when found). ELF quirk kept: a second Load (loadCount) appends 143 more CAnimAuxData without clearing the list. The scan's 136 "port string" items are GCC inlining InitializeAnimNames into this body. |
| 4 | 0x2ccad0 | 1744 | AnimSet::Load(_zrdr*) | gamez/zAnim/anim.cpp | MATCH | - | Whole range 0x2ccad0-0x2cd1a0 compared. Inlined AnimSet ctor (new 132; m_ready, m_animgps = 0, eight `new CBlendable` + Clear at +0x64..+0x80 in order) = the header's inline ctor. m_ready cleared again, m_name.assign, strcmp "defusebomb anim set" -> m_defuse, -1 pushed to m_animIDs and m_basetypes (words 0x475090..9c all -1). include: flat_findtag_startidx(.., 0), array test (type 4), loop i < integer - 1 via Get, string (type 3) entries appended = the port's Get(i) loop. anim_set_anims loop i = 1 .. < array[0].integer: type 0 when type_name is missing, else (s16) FindAnimType (inlined: -1 for a NULL string or no entry); a negative type takes numAnimTypes++, is entered in newNamesMap and gets a new CAnimAuxData appended; id = animNamesMap[anim_name] (inserting) when > 0 else -1 (ELF quirk kept, already noted in the code); grow loop tests m_animIDs size only and pushes both; m_animIDs[type] = id, m_basetypes[type] = type; network_log present -> list[type] bit 0 = 1. Set appended to list, returns 1 (0 without anim_set_name). The scan's "ELF calls operator new 10 times, port twice" is the ctor GCC did not inline. |
| 2 | 0x2c7ef0 | 17612 | InitializeAnimNames() | gamez/zAnim/anim.cpp | MATCH | - | Whole range 0x2c7ef0-0x2cc3bc compared. 157 inlined FindAnimType blocks, all one shape (string NULL test, newNamesMap.find, node value read as `lh +0x10` or -1, `sh` to the static); (string, static) pairs extracted by script and compared with the port's 157 lines in order: all equal. ELF quirks kept and now commented in the code: MovingPistol2Rifle looks up "Moving rifle -> Pistol" (0x456310, the MovingRifle2Pistol string) and CQBVictimFallBackwards looks up "Death stand head01" (0x4565d0). The port's out-of-line FindAnimType returns the int value, cut to short: the same as the ELF's `lh`. The scan's "+0x10 / +0x18" is the map node layout of each library. |
