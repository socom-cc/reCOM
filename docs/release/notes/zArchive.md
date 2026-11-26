# Stage 2: gamez/zArchive (2026-11-25)

Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`, the function map
at HEAD 66a46051). Checked by `socom-release-check-z1`, who did not write the tool.

Scope: the 86 rows of `function-map.tsv` whose owner file is under `gamez/zArchive`, plus the
release functions sitting between them. Every row was checked, the 31 exact ones included: both
sides disassembled (objdump of the loaded images), calls named through the map, and callers found
by scanning both images for `jal`/`j` to the function. Ghidra was not needed.

Evidence that settled rows, in the order it was used: the callers of a function and the call
site inside an already paired caller (same offset in both builds); the `__FILE__`/`__LINE__`
arguments of the debug allocators (`zar_main.cpp`, `zar_search.cpp`); the slot between two
paired neighbours; the prototype source and DWARF (`zar::CZAR` 164 bytes, `zar::CKey` 24 bytes,
`TAIL` 96 bytes).

## Checked rows

Release address, prototype address and function, the tool's class, the verdict, the reason.
"Container" below means the change of `zar::CKeyRing` from `std::list<CKey*>` to
`std::vector<CKey*>` (see What changed).

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1d9780 | 0x1d9910 `CZAR::SetFilename(const char*)` | unsure | corrected to new; 0x1d9910 removed | 0x1d9780 appends bytes to the memory write buffer at +0x30 (calloc/realloc at zar_main.cpp lines 1108/1109, memcpy), called only by `Insert(CKey*,…)`; the pair came from the file-name string |
| 0x1d9930 | 0x1d7ff0 `CZAR::NewKey(const char*)` | deviating | confirmed | offsets only (m_stable +0x8c→+0x9c, m_key_buffer +0x94→+0xa4); the temporary key's destructor is now 0x1d9a70 |
| 0x1d9ae0 | 0x1d8130 `CKey::~CKey()` | unsure | confirmed, deviating | same callers at the same offsets (`vector_imp<CKey>::insert` +0x4e0, `reserve` +0x190); bytes equal, the base destructor called is `__vector_pod<Ui>`'s instead of `list_deleter`'s (container) |
| 0x1d9b50 | 0x1d81a0 `CZAR::WriteDirectory()` | unsure | confirmed, deviating | called by `Close()`, same slot, zar_main.cpp strings; body rewritten for the new file layout |
| 0x1d9f70 | - | new | corrected to 0x1d8480 `_countKeys(CKey*)` | same slot after WriteDirectory, recursive, called by WriteDirectory where the prototype calls `_countKeys`; same three nested loops over a vector |
| 0x1da0a0 | - | new | corrected to 0x1d8600 `CKey::fixupKey(CSTable*, void*)` | its address is the function pointer WriteDirectory passes to `CSTable::Pack` (the prototype passes `fixupKey`); recursive; `FindString` on the names |
| 0x1da1e0 | 0x1d8740 `CZAR::ReleaseDataBuffer()` | deviating | confirmed | offsets only: m_databuffer +0x18→+0x1c |
| 0x1da250 | 0x1d87b0 `CZAR::ReadDirectory(int, unsigned)` | unsure | confirmed, deviating | same callers (`Open`), same calls in order (Unsecurify, CSTable Destroy/LoadTable, key vector clear/reserve, CBufferIO), zar_main.cpp strings; reads the record from the front |
| 0x1da780 | 0x1d8cd0 `CZAR::GetSize(const char*)` | deviating | confirmed | open-key stack top is `back()` of a vector (was `front()` of a list); m_root +0x88→+0x98 |
| 0x1da800 | 0x1d8d30 `CZAR::GetOpenKey()` | deviating | confirmed | as GetSize |
| 0x1da830 | 0x1d8d60 `CZAR::OpenKey(CKey*)` | deviating | confirmed | `push_front` on a list became `insert(end)` on a vector |
| 0x1da890 | 0x1d8dd0 `CZAR::FindKey(const char*)` | deviating | confirmed | as GetSize |
| 0x1da900 | 0x1d8e30 `CZAR::OpenKey(const char*)` | deviating | confirmed | `back()` and `push_back` on the vector; m_root offset |
| 0x1da9d0 | 0x1d8f00 `CZAR::CloseKey(CKey*)` | deviating | confirmed | `pop_front` (list erase) became an inline `pop_back` (size − 1) |
| 0x1daa30 | 0x1d8f70 `CZAR::CreateKey(const char*)` | deviating | confirmed | offsets (+0x10 for m_stable, m_key_buffer, m_root) and the vector `back()`/`push_back` |
| 0x1dac10 | 0x1d9160 `list<CKey*>::~list()` | deviating | confirmed by role | called at the same sites (CreateKey +0xc4/+0x110, `vector_deleter<CKey>::clear` +0x54); body is now a vector destructor (frees +0x8), so the prototype name does not carry over |
| 0x1daca0 | 0x1d91f0 `vector_deleter<CKey>::data()` | exact | confirmed | equal |
| 0x1dacb0 | 0x1d9200 `CZAR::Open(const char*, int, unsigned, unsigned)` | unsure | confirmed, deviating | the same 15 call sites in both builds (LoadWorld, CZAnimMain, zBoneOpen, ReadClutter, CSaveLoad, CSnd, CZWeapon, CSaveManager); gained a fifth argument; Close() no longer inline |
| 0x1daec0 | 0x1d9560 `CZAR::ReOpen(int, unsigned)` | deviating | confirmed | same three callers; now only `if open return true; return Open(m_filename, appver, mode, 16, false)` |
| 0x1daf50 | 0x1d9680 `CZAR::Close(bool)` | unsure | confirmed, deviating | the one caller (LoadWorld) is the same; adds the temp-file close and clears the open-key stack |
| 0x1db0e0 | 0x1d9480 `vector_deleter<CKey>::swap` | exact | confirmed | equal |
| 0x1db140 | 0x1d9540 `vector_deleter<CKey>::vector_deleter()` | exact | confirmed | equal |
| 0x1db160 | 0x1d97a0 `CZAR::Close()` | deviating | confirmed | all 20 outside call sites match one for one |
| 0x1db360 | 0x1d98f0 `CZAR::CloseKeepDir()` | exact | confirmed | equal |
| 0x1db380 | 0x1d99a0 `CZAR::~CZAR()` | deviating | confirmed | Close() now called, not inlined; root deleted through 0x1d9a70; m_keys destroyed by `__vector_pod<Ui>` |
| 0x1db500 | 0x1d9c50 `CZAR::CZAR(const char*, CIO*)` | deviating | confirmed | offsets; zeroes the new +0x18 and +0x30 and +0x2c; memset 100 (was 96); version 0x20002 (was 0x20001); m_keys built by `__vector_pod<Ui>` ctor |
| 0x1db6e0 | 0x1d9e10 `CKeyRing::~CKeyRing()` | deviating | confirmed | calls the `__vector_pod<Ui>` destructor instead of a list erase |
| 0x1db750 | 0x1d9eb0 `CZAR::DoMemAlign(bool)` | exact | confirmed | equal ($gp offset masked) |
| 0x1db760 | 0x1d9ec0 `CZAR::DoMemAlign()` | exact | confirmed | equal |
| 0x1db770 | 0x1d9ed0 `vector_imp<CKey>::insert` | exact | confirmed | equal; its callees at +0x24c/+0x284 are 0x1dbd10/0x1dbce0 |
| 0x1dbcb0 | 0x1da410 `compressed_pair_imp<allocator<CKey>,Ui,1>::first` | exact | confirmed | equal |
| 0x1dbcc0 | 0x1da420 `compressed_pair_imp<allocator<CKey>,Ui,1>::swap` | exact | confirmed | equal |
| 0x1dbce0 | 0x1da440 `list_imp<PCv>::operator=` | unsure | confirmed by role, deviating | called at `vector_imp<CKey>::insert` +0x284 in both; now a 10-instruction wrapper of `__vector_pod<Ui>::operator=` (container); name does not carry over |
| 0x1dbd10 | 0x1da4f0 `list<CKey*>::operator=` | unsure | confirmed by role, deviating | called at `insert` +0x24c in both; same wrapper as 0x1dbce0 |
| 0x1dbd40 | 0x1da5a0 `list_imp<PCv>::list_imp(const&)` | deviating | confirmed by role | the 7 call sites in insert/reserve match; wraps `__vector_pod<Ui>`'s copy ctor |
| 0x1dbd70 | 0x1da5f0 `vector_imp<CKey>::reserve` | exact | confirmed | equal |
| 0x1dbf60 | 0x1da7e0 `vector_deleter<CKey>::clear` | exact | confirmed | equal |
| 0x1dbff0 | 0x1da870 `vector_deleter<CKey>::~vector_deleter` | exact | confirmed | equal |
| 0x1dc390 | 0x1dabe0 `list_imp<PCv>::init<…>` | exact | confirmed | equal; no zArchive caller left (callers in zNode and zTwoD) |
| 0x1dc4e0 | 0x1dad30 `compressed_pair_imp<allocator<PCv>,Ui,1>::first` | exact | confirmed | equal |
| 0x1dc4f0 | 0x1dad40 `alloc_ptr<…node…>::get` | exact | confirmed | equal |
| 0x1dc500 | 0x1dad50 `compressed_pair_imp<allocator<node>&,…>` ctor | exact | confirmed | equal |
| 0x1dc520 | 0x1dad70 `compressed_pair<number<Ui,1>,node*>` ctor | exact | confirmed | equal |
| 0x1dc540 | 0x1dad90 `allocator<list_deleter node>::allocate` | exact | confirmed | equal |
| 0x1dc5a0 | 0x1dadf0 `compressed_pair_imp<allocator<node>,node_base,1>::first` | exact | confirmed | equal |
| 0x1dc5b0 | 0x1dae00 `list_deleter<PCv>::list_deleter(const allocator&)` | exact | confirmed | equal |
| 0x1dc5d0 | 0x1daf80 `CZAR::FetchLIP(CKey*, void**)` | exact | confirmed | equal (seeks `key->m_offset` without the new data base) |
| 0x1dc6f0 | 0x1db0a0 `CZAR::Fetch(CKey*, void*, int, unsigned)` | deviating | confirmed | seeks `m_dataStart(+0x2c) + key->m_offset`; m_bSecure +0xa1→+0xb1 |
| 0x1dc8d0 | 0x1db270 `CZAR::Securify(void*, int)` | deviating | confirmed | only m_bSecure +0xa1→+0xb1 |
| 0x1dc9a0 | 0x1db340 `CZAR::Unsecurify(void*, int)` | deviating | confirmed | only m_bSecure +0xa1→+0xb1 |
| 0x1dca70 | 0x1db410 `CZAR::Insert(CKey*, const void*, int)` | deviating | confirmed | logic changed: data goes to the temp file or the memory buffer, not the archive file (see below) |
| 0x1dcdd0 | 0x1db680 `CZAR::Insert(const char*, const void*, int)` | unsure | confirmed, deviating | bytes equal; the failed key's destructor is now 0x1d9a70 (container) |
| 0x1dce90 | 0x1db880 `CZAR::FetchAll(…)` | deviating | confirmed | vector iteration inline; returns the count of accepted keys (was `count != 0`) |
| 0x1dd000 | 0x1dba10 `CZAR::Fetch(const char*, int(*)(CZAR&,int,void*), void*)` | exact | confirmed | equal (no data base added) |
| 0x1dd120 | 0x1dbb30 `CZAR::Fetch(const char*, void*, int)` | deviating | confirmed | seeks data base + offset; register allocation changed |
| 0x1dd270 | 0x1dbc70 `CZAR::FetchString(const char*, char*, int)` | deviating | confirmed | seeks data base + offset |
| 0x1dd3e0 | 0x1dbdd0 `CZAR::Fetch(const char*, char**)` | exact | confirmed | equal |
| 0x1dd4e0 | 0x1dbed0 `CZAR::Fetch(const char*, float*)` | exact | confirmed | equal |
| 0x1dd560 | 0x1dbf50 `CZAR::Fetch(const char*, unsigned*)` | exact | confirmed | equal |
| 0x1dd5e0 | 0x1dbfd0 `CZAR::Fetch(const char*, int*)` | exact | confirmed | equal |
| 0x1dd660 | 0x1dc050 `CZAR::Fetch(const char*, bool*)` | exact | confirmed | equal |
| 0x1dd6f0 | 0x1dc0e0 `CKey::FindKey(const char*)` | deviating | confirmed | the loop runs over the vector inline (was list iterator calls); same strcasecmp and size −1 test |
| 0x1dd7c0 | - | new | corrected to 0x1dc1d0 `CKey::Read(CZAR*, CIO*, int)` | same slot after CKey::FindKey; called by ReadDirectory at the place of `Read`; recursive; reads the 16-byte record |
| 0x1dd8e0 | - | new | corrected to 0x1dc2d0 `CKey::Write(CZAR*)` | same slot; called by WriteDirectory; recursive; writes the same four secured words |
| 0x1dda40 | - | new | confirmed | returns 16 (the key record size); called by WriteDirectory |
| 0x1dda50 | - | new | confirmed | recursive key count with a flag; called by WriteDirectory |
| 0x1ddb40 | 0x1dc450 `CKey::InsertKey(CKey*)` | deviating | confirmed | `push_back` is now `__vector_pod<Ui>::insert(end, 1, &key)` |
| 0x1ddb90 | 0x1dc4a0 `CKey::CKey()` | unsure | confirmed, deviating | bytes equal; base ctor is `__vector_pod<Ui>`'s (container) |
| 0x1ddbd0 | 0x1dc4e0 `CKey::CKey(const char*)` | unsure | confirmed, deviating | as above |
| 0x24efd0 | 0x1da930 `list_imp<PCv>::do_assign<…>` | deviating | confirmed; owner moves | only caller `CCharacterType::CCharacterType(const char*, const CCharacterType*)` in both; now calls the range ctor/`init` instead of an inline loop; placed among char_type.cpp's functions, so no longer a zArchive contribution |
| 0x250060 | 0x1dae20 `list_imp<PCv>::advance_to` | exact | confirmed; owner moves | equal; placed among char_type.cpp's functions |
| 0x2500f0 | 0x1daeb0 `__advance<…list iterator…>` | exact | confirmed; owner moves | as above |
| 0x250240 | 0x1daf10 `list_deleter<PCv>::splice` | exact | confirmed; owner moves | as above |
| 0x2503c0 | 0x1dabc0 `list_deleter<PCv>::alloc` | exact | confirmed; owner moves | as above |
| - | 0x1d8470 `list<CKey*>::generic_iterator` ctor | removed | confirmed | list iterator; no list left in CKeyRing |
| - | 0x1d8480 `_countKeys(CKey*)` | removed | corrected to 0x1d9f70 | see 0x1d9f70 |
| - | 0x1d8600 `CKey::fixupKey(CSTable*, void*)` | removed | corrected to 0x1da0a0 | see 0x1da0a0 |
| - | 0x1d94e0 `vector_imp<CKey>::~vector_imp` | removed | confirmed | its callers (Open, ~CZAR with Close inlined) now call `Close()` and `vector_deleter<CKey>` destructor |
| - | 0x1d9740 `std::swap<CKey>(vector_deleter&, vector_deleter&)` | removed | confirmed | inlined: Close, Close(bool) and ~CZAR call `vector_deleter<CKey>::swap` directly |
| - | 0x1daba0 `list_deleter<PCv>::generic_iterator<1>::operator*` | removed | confirmed | used only by the old do_assign loop |
| - | 0x1dabb0 `allocator<list_deleter node>` ctor | removed | confirmed | as above |
| - | 0x1dabd0 `allocator<PCv>` copy ctor | removed | confirmed | as above (release do_assign calls the list_deleter ctor) |
| - | 0x1db740 `CZAR::Insert(const char*, unsigned)` | removed | confirmed | its only callers, `CSubMesh::Write` (removed) and `CMesh::Write` (release 0x3129b0 no longer calls it), dropped the use |
| - | 0x1db7e0 `CZAR::Insert(const char*, int)` | removed | confirmed | as above |
| - | 0x1dc1d0 `CKey::Read(CZAR*, CIO*, int)` | removed | corrected to 0x1dd7c0 | see 0x1dd7c0 |
| - | 0x1dc2d0 `CKey::Write(CZAR*)` | removed | corrected to 0x1dd8e0 | see 0x1dd8e0 |
| 0x1d9a70 | 0x21b800 `CCheatList::~CCheatList()` (gamez/zInput) | unsure | corrected to new | called by NewKey, ~CZAR, Insert(const char*,…) and CSaveManager::Save at the places the prototype destroys a CKey through `list_imp<PCv>::~list_imp`; frees the buffer at +0x8: the destructor of the vector behind CKeyRing; the pair was a global look-alike match |

Release functions between the module's rows that the map does not give to zArchive:

| release | map | finding |
|---|---|---|
| 0x1d9740 | new, no owner | not zArchive: a deque/ring helper called by 0x1d91e0 and the `CCnfStateMachine` deque destructor; leave to the preceding module |
| 0x1db080 | exact `__vector_pod<Ui>::swap` (prototype in body.cpp) | correct pair; in the release it is emitted with zar_main.cpp (first callers: Close, Close(bool)) |
| 0x1dc0b0, 0x1dc100, 0x1dc150, 0x1dc250 | exact `__vector_pod<Ui>` `operator=`, copy ctor, `init`, `do_assign` (prototype in fts_mission.cpp) | correct pairs; emitted with zar_main.cpp in the release (called by 0x1dbce0, 0x1dbd10, 0x1dbd40) |
| 0x1dc380 | exact `list_deleter<PCv>::end` (no owner) | correct pair; no zArchive caller |

## Settled pairs (tool input)

Rows whose class or counterpart differs from the map, or that the map left unsure.

| release | prototype | basis |
|---|---|---|
| 0x1d9780 | new | callers: `Insert(CKey*,…)` only; zar_main.cpp lines 1108/1109 |
| removed | 0x1d9910 | out-of-line copy only called by ReOpen, which now calls Open; inline in Open, CZAR, ~CZAR (zar_main.cpp lines 102/109) |
| 0x1d9a70 | new | call sites of the CKey destructor in NewKey, ~CZAR, Insert |
| 0x1d9ae0 | 0x1d8130 | call sites in insert +0x4e0, reserve +0x190 |
| 0x1d9b50 | 0x1d81a0 | caller Close(); slot; strings |
| 0x1d9f70 | 0x1d8480 | call site in WriteDirectory; slot; recursion |
| 0x1da0a0 | 0x1d8600 | function pointer passed to `CSTable::Pack` in WriteDirectory; slot |
| 0x1da250 | 0x1d87b0 | caller Open; call order; strings |
| 0x1dacb0 | 0x1d9200 | 15 matching outside call sites |
| 0x1daf50 | 0x1d9680 | caller LoadWorld |
| 0x1dbce0 | 0x1da440 | call site in insert +0x284 |
| 0x1dbd10 | 0x1da4f0 | call site in insert +0x24c |
| 0x1dcdd0 | 0x1db680 | bytes equal; callers |
| 0x1dd7c0 | 0x1dc1d0 | call site in ReadDirectory; slot; recursion |
| 0x1dd8e0 | 0x1dc2d0 | call site in WriteDirectory; slot; recursion |
| 0x1ddb90 | 0x1dc4a0 | bytes equal; slot |
| 0x1ddbd0 | 0x1dc4e0 | bytes equal; slot |

All of these are deviating except the `new`/`removed` lines. The other 69 rows stand as the map
has them.

## What changed

### Layouts

`zar::CKeyRing` (the base of `zar::CKey` and the type of `CZAR::m_keys`) is a
`std::vector<CKey*>` in the release, not a `std::list<CKey*>`. Every list call in the module is
replaced by `__vector_pod<unsigned>` calls or inline vector code (size at +0x4, data at +0x8,
both relative to the container). The size stays 12, so `zar::CKey` stays 24 bytes (`m_name`
+0xc, `m_size` +0x10, `m_offset` +0x14; `vector_imp<CKey>::insert`/`reserve` are byte-equal).
The open-key stack keeps its innermost key at the back now. Shown by: GetSize, GetOpenKey, both
OpenKey, FindKey, CloseKey, CreateKey, CKeyRing and CKey constructors/destructor, CKey::FindKey,
InsertKey, _countKeys, fixupKey, CKey::Read/Write, WriteDirectory, Close, Close(bool), ~CZAR,
and the operator=/copy-ctor wrappers 0x1dbce0, 0x1dbd10, 0x1dbd40.

`zar::CZAR` grows from 164 to 180 bytes (`operator new(180)` at the three construction sites;
164 in the prototype):

| release | member | prototype |
|---|---|---|
| +0x04 | m_keys (now a vector) | +0x04 |
| +0x10 / +0x14 | m_pFileAlloc / m_pFile | same |
| +0x18 | new: `CIO*` temp-file stream (`<base>_tmp.<ext>`, see Open) | - |
| +0x1c / +0x20 | m_databuffer / m_databuffer_size | +0x18 / +0x1c |
| +0x24 | m_modified | +0x20 |
| +0x28 | m_data_padded | +0x24 |
| +0x2c | new: file position of the data area (0 once the data is in memory) | - |
| +0x30 | new: pointer to a 16-byte write buffer {data, capacity, used, grow count} | - |
| +0x34 | the directory record, 100 bytes (below) | +0x28 m_tail, 96 bytes |
| +0x98 / +0x9c / +0xa0 | m_root / m_stable / m_filename | +0x88 / +0x8c / +0x90 |
| +0xa4 | m_key_buffer | +0x94 |
| +0xb0 / +0xb1 | m_bCompress / m_bSecure | +0xa0 / +0xa1 |

Shown by: the constructor (zeroes +0x18, +0x2c, +0x30; memset 100 at +0x34), ReadDirectory,
WriteDirectory, Insert(CKey*), Close, Open, Fetch(CKey*,…), Securify/Unsecurify (+0xb1 only),
ReleaseDataBuffer (+0x1c only), NewKey/CreateKey (+0x9c, +0xa4).

The directory record is the prototype's `TAIL` (DWARF, 96 bytes) with one word inserted at +0x10:

| offset | field | evidence |
|---|---|---|
| +0x00 .. +0x0c | flags, key_count, stable_size, stable_ofs | as TAIL |
| +0x10 | new: the data alignment | WriteDirectory stores m_data_padded there; ReadDirectory uses it as the modulus of the padding before the data |
| +0x14 | reserved[16] | as TAIL |
| +0x54 .. +0x60 | offset (now the size of the data area), crc, appversion, version | version 0x20002 is required (was 0x20001) |

The user's fact holds for position and content: the record is written first and read first
(`fseek(0, SEEK_SET)`, `fread(100)`, version check), and it holds the alignment word. Two parts
are not shown by the code: the name `zar::HEAD` (the release has no symbols or RTTI for it; the
port's `zar.h` already declares a `zar::HEAD` with exactly this 100-byte layout, but the
prototype's DWARF has only `TAIL`), and the type `u32`. Both divisions that use the alignment
are signed (`div` in ReadDirectory and WriteDirectory), while `Insert(CKey*)` uses `divu` on the
unsigned m_data_padded; so the field reads as signed (`s32`), or the source casts it. Flag the
`u32` as a guess until a use shows it.

File layout, from ReadDirectory and WriteDirectory: the 100-byte record, the string table
(stable_size bytes), the key records (16 bytes each), padding up to a multiple of the alignment
('P', or 0xaf when secured), then the data. Key data offsets are relative to the data area;
ReadDirectory records its file position at +0x2c.

### Functions

| function | change |
|---|---|
| NewKey | offsets only (+0x10); temporary key destroyed by 0x1d9a70 |
| _countKeys (0x1d9f70) | same counting, over vectors |
| fixupKey (0x1da0a0) | same full-tree fix-up; inlined one level deeper (key, children, grandchildren, then recursion) |
| WriteDirectory | logic changed: version 0x20002; alignment = m_data_padded; offset = bytes in the write buffer; writes record, string table, keys (CKey::Write), padding, then copies the data from the temp file in 16 MB chunks or writes the memory buffer; returns 0 (was true) |
| ReleaseDataBuffer | offset only (+0x4) |
| ReadDirectory | logic changed: record read at offset 0, 100 bytes, version 0x20002; string table and keys follow without a seek; key count clamped by CKey::Read; padding skipped with `fseek(SEEK_CUR)`; data read from the current position; data position kept at +0x2c (0 after the switch to the memory stream) |
| GetSize, GetOpenKey, FindKey, OpenKey ×2, CloseKey, CreateKey | container (front of a list → back of a vector) and m_root/m_stable/m_key_buffer offsets |
| Open | gained a fifth argument (in `$t1`): when set, also opens `<name up to '.'>_tmp.<rest>` (strtok, strcat; strings `.` and `_tmp.`) in a new `CFileIO` at +0x18, mode 0x3c; Close() no longer inlined; SetFilename inline |
| ReOpen | logic changed: delegates to `Open(m_filename, appver, mode, 16, false)` |
| Close(bool) | adds closing/deleting the temp file; clears root children by swapping with an empty vector; also clears m_keys |
| Close() | as Close(bool), plus the write-buffer free (zar_main.cpp line 1067) |
| ~CZAR | Close() called instead of inlined; m_root deleted through 0x1d9a70 |
| CZAR() | offsets; new members zeroed; version 0x20002; record size 100 |
| ~CKeyRing, CKey(), CKey(const char*), ~CKey | base container changed; otherwise equal |
| Fetch(CKey*,…), Fetch(name, void*, int), FetchString | seek to data base (+0x2c) + key offset |
| Securify, Unsecurify | m_bSecure offset only (+0x10) |
| Insert(CKey*,…) | logic changed: no archive-file seek; data (inverted copy when secured, the unrolled 8-byte loop of `ZAR_SECURE`) goes to the temp file or to the memory buffer (0x1d9780); key offset = position in that store; padding written there too (divu by m_data_padded) |
| Insert(const char*, const void*, int) | callee of the failure path only |
| FetchAll | vector iteration; returns the count, not a bool |
| CKey::FindKey, InsertKey | container |
| CKey::Read (0x1dd7c0) | reserves the child count first, treats a negative count as 0 |
| CKey::Write (0x1dd8e0) | secures, writes and unsecures each field in place (name, offset, size), then the child count from a local |
| list `do_assign` (0x24efd0) | calls the range ctor/`init` instead of an inline loop; emitted outside zArchive now |

A release quirk to keep: FetchLIP, `Fetch(name, callback, …)` and FetchAll seek `key->m_offset`
without the +0x2c data base, so they only work once the data is in memory (base 0).

## New and removed

New in the module:

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x1d9780 | appends n bytes to the write buffer at +0x30, creating the 16-byte buffer on first use and growing it with calloc/realloc; returns n | `zar::CZAR::BufferWrite(const void*, int)` — guess from use: the memory counterpart of `fwrite` in Insert(CKey*) |
| 0x1d9a70 | destroys a vector of pointers: frees +0x8, deletes itself when asked | the destructor of CKeyRing's `std::vector<CKey*>` (guess at the template level; the map's name `CCheatList::~CCheatList` is wrong) |
| 0x1dda40 | returns 16 | `zar::CKey` record size, e.g. `GetRecordSize()` — guess; WriteDirectory multiplies the key count by it |
| 0x1dda50 | counts this key and, when its flag is true, all keys below it (recursive) | `zar::CKey::CountKeys(bool recursive)` — guess from the body; WriteDirectory calls it with (root, true) for the padding |

Removed: `SetFilename` (out of line; ReOpen delegates to Open, the other users had it inline),
`list<CKey*>::generic_iterator` ctor, `vector_imp<CKey>::~vector_imp`, `std::swap<CKey>`
(inlined into the member swap calls), the three list helpers of the old do_assign, and
`Insert(const char*, unsigned)` / `Insert(const char*, int)` (no caller left: `CSubMesh::Write`
removed, `CMesh::Write` changed). `_countKeys`, `fixupKey`, `CKey::Read` and `CKey::Write` are not
removed; they are paired above.

## Still unsure

None of the module's rows. Two things are open:

- The exact template names of the vector functions that replaced the list ones (0x1d9a70,
  0x1dac10, 0x1dbce0, 0x1dbd10, 0x1dbd40): their roles are settled by call sites, their
  spelling is not, so stage 3 should not carry over the prototype's list names for them.
- The type of the record's alignment word (signed by its divisions; `u32` per the user).

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| exact | 31 | 31 | 0 |
| deviating | 26 | 26 | 0 |
| unsure | 11 | 9 counterparts right (now deviating) | 2: 0x1d9780 (SetFilename), 0x1d9a70 (CCheatList) |
| new | 6 | 2 | 4: 0x1d9f70, 0x1da0a0, 0x1dd7c0, 0x1dd8e0 have counterparts |
| removed | 12 | 8 | 4: the same four counterparts |

Owner attribution: five `zar_main.cpp` list templates (do_assign, advance_to, __advance, splice,
alloc) sit among char_type.cpp's functions in the release, and five `__vector_pod<Ui>` functions
the map gives to body.cpp/fts_mission.cpp are emitted with zar_main.cpp.

What misled it:

- The four removed/new pairs: the container change rewrote every call, so the bodies fell
  below the similarity thresholds (0.23–0.45), and their callers (ReadDirectory, WriteDirectory)
  were only unsure, so no call-tree propagation reached them. The same slot between paired
  neighbours, the call site in the paired caller, self-recursion and the `CSTable::Pack`
  function pointer all pointed to the right pair.
- SetFilename ↔ 0x1d9780: string evidence. `zar_main.cpp` (the `__FILE__` of the debug
  allocators) is shared by many functions, but uniqueness is counted among the functions still
  unpaired, where it was left on these two.
- CCheatList ↔ 0x1d9a70: a global look-alike among small destructors (0.83, flagged ambiguous);
  its callers are all zArchive and CSaveManager, none near zInput.
- The call-conflict rows (CKey ctors/dtor, Insert(const char*,…)) were flagged correctly: the
  bytes are equal but the callees switched from list to vector functions. They are real pairs.

What would make the next modules cheaper:

- Propagate call correspondences from deviating and unsure pairs too, by aligning their ordered
  call lists, and count `lui`/`addiu` of a code address (function pointers) as a call. That
  alone would have settled all four wrong new/removed pairs and most unsure rows.
- Count string uniqueness over all functions, not over the unpaired ones, and ignore source-file
  name strings for pairing.
- Print, per non-exact row, both sides' ordered call lists mapped through the pairs, the callers
  of each side, and the immediate deltas per base register (+0x10 on `s0`, ...). With those
  three, a deviating row is a glance, and a layout change shows as one repeated delta.
- Report a family change as one finding: here about 20 rows change only because `list_deleter`
  calls became `__vector_pod<Ui>` calls.
- Give a moved template instance the owner of its release neighbours, with a flag.

Time per row (a scripted side-by-side plus a caller scan, both read-only): exact about half a
minute, checked in one batch; deviating 1–2 minutes; unsure 3–5 minutes; new and removed about 4
minutes, mostly settled in groups once the callers were known. ReadDirectory, WriteDirectory and
Insert, which carry the format change, took about 15 minutes together.
