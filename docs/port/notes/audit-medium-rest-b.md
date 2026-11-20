# Audit of list medium-rest-b (2026-11-19, socom-port-audit-mrest-b)

The 90 medium functions (33,148 bytes) of zArchive (zar_main.cpp, zar_search.cpp), zBody (body.cpp,
zbody_main.cpp), zEntity (ent_entity.cpp, ent_main.cpp, ent_target.cpp, pickup_main.cpp) and
zTexture (ztex_handle.cpp, ztex_main.cpp, ztex_manager.cpp, ztex_read.cpp). HEAD 61ad60d1. Judged
file by file in the scan's rank order, each over its whole range with the helpers the ELF inlines
(SetFilename, Close, NewKey's storage rule, Securify, the CGSTexBuffer / CZBodyPart / CBlendOverlay
constructors and destructors, ACTIVE_ANIM::Clear, Snap, SetTexture, CPickup::Create); addresses
cited from `ref.dis`.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 77 |
| DEFECT-FIXED | 13 (A 0, B 1, C 12) |
| DEVIATION-KEPT | 0 |
| UNJUDGED | 0 |

Defect rate 13 / 90 (14%); B 1.

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #64, #65, #66, #67 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).

## Fixes

- B #70 `CTexList::Append` 0x2f8860: a new handle is appended (insert at data + size, 0x2f8938);
  the port inserted it first. Every asset library's texture list (AddTexture) now keeps the
  ELF's order, which CGSTexBuffer::Add / MakeChain lay out in the GS and GetHandle searches.
- C #71 `CTexList::GetHandle(const char *)` 0x2f8960: compares the texture's own name (texture
  +0x14, 0x2f89c0), not the handle's copy.
- C #69 `CTexHandle::Create` 0x2f97e0: the inlined SetTexture's _free / _strdup with
  "ztex_handle.cpp" lines 91 / 92 (0x2f9848 / 0x2f9864); the port used zfree and libc strdup.
- C (NaN forms, c.le / c.lt with the bc1t sense): #36 `CBlendOverlay::Trigger` !(interp1 <= 0)
  (0x1e176c, the lead from audit-large-rest); #37 `CBlendOverlay::IsTriggerTime` the backward wrap
  (to - 1) <= t (0x1e18cc) and the forward wrap on to < from (0x1e1900); #34
  `CZBodyAnimBlend::IsTriggerTime` the forward wrap on to < from (0x1e0848); #38
  `CZBodyAnim::SetMultiplier` !(distance <= 0.2) (0x1e1c78); #33 `CZBodyAnimBlend::Propagate`
  !(playback <= 0) (0x1e047c); #31 `CZBodyAnimBlend::GetVelocity` !(playback <= 0) (0x1e0078).

## Kept deviations (reasons in the code)

- #66 `CPickup::Create`: the NULL test after a failed allocation.
- #67 `CPickup::NetworkCreate`: NULL while closed (the ELF writes the net id through NULL).
- #64 `CPickup::GetClosest`, #65 `CPickup::GetNext`: a pickup without a node is skipped (the ELF
  subtracts from address 0).

ELF quirks kept (in the code or noted in the rows): #51 / #52 the first entity's PrePostTick /
PostPreTick only; #59 the in-loop counter clearing; #26 Top read once; #33 dT scaled
cumulatively; #29 the pool size tested; #25 the global list swapped; #68 GetMPBomb after the
list was emptied; #85 a palette pushed again after Add; #57 the unread bool return.

Float checks: #60 / #58 / #64 / #65 distances (x x + y y) + z z through adda / madd; #32 / #33 the
wrap and clamp forms; #31 / #41 the operand orders of the weighted sums and the lerp; #39 / #38 the
division orders; literals 0x3e4ccccd, 0x3727c5ac, 0x49742400, 0x3f800000 equal to the port's
spellings. fptoui in #79 / #84 (the buffer range): never negative here (texture base 0x2bc0,
fractions >= 0), so GCC's (u32) agrees.

## Leads for other lists

- With #70 fixed, the GS layout order of every library's textures follows the ELF; the
  medium-node fixes of AddTexture / AddModel and the `AddPalette` lead (0x231000 appends) are the
  same family.
- `CBits::GetWordCount` 0x17fbf0 is (bits >> 5) + 1, the same as Create's inline memset size.

## What the packets lacked

The list layout behind `tail()` (MW list: the sentinel at list +4, its next at +8; read from
0x17bbc0 with dis.sh); the caller's use of RecycleEntity's return (0x1fcbd4); CBits::GetWordCount;
the GP words of Normalize's _close_enough (fl.py); the port's CActiveAnimPool::PutBack /
CZBodyPart ctor / CBody::Snap bodies (other functions in the file, found with grep); the
textureBaseAddr value for the fptoui check; several cited addresses differed from the compacted
listings (taken from `ref.dis`).

## Runs

- Default build links (`default.sh audit-mrest-b-def1`: library 0 errors, link 0 undefined; the
  tree checked to hold the three edited files).
- `gate.ps1 -Only roundtrip -Build audit-mrest-b-gate` (loading changes: the texture lists; the
  body fixes run in the mission), on 83cf67db + these files: PASS, 4 returns, in use 18,657,916 B
  flat; no STOP, TLB miss or assert. No targeted trace: the B fix only reorders a list and is
  exercised by every library load of the round trip.

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 50 | 0x1ee440 | 348 | CEntity::TeleportTo(CPnt3D const*, CQuat const*) | ent_main.cpp | MATCH | | node matrix copied to a local; m_velW, m_velM, m_velR, m_next_velw zeroed; pos into row 3; rot into m_next_quat and m_quat, then ToMatrix into the local; the local into m_next_matrix (+0x80) and SetMatrix. The port's CMatrix ctor is overwritten by the copy |
| 48 | 0x1ee190 | 244 | CEntityList::GetEntityById(unsigned int) const | ent_main.cpp | MATCH | | invalidId gives NULL; first entity whose m_id equals; NULL |
| 49 | 0x1ee290 | 252 | CEntityList::GetEntity(char const*) const | ent_main.cpp | MATCH | | NULL name gives NULL; strcasecmp(name, node name +0x90) per entity in order |
| 51 | 0x1eec70 | 312 | CEntity::PostTickAll(float, void*) | ent_main.cpp | MATCH | | slot 0x1c PrePostTick on the first entity only (quirk kept), slot 0x20 PostTick on each; false |
| 52 | 0x1eedb0 | 312 | CEntity::TickAll(float, void*) | ent_main.cpp | MATCH | | slot 0x18 PostPreTick on the first entity only (quirk kept), slot 0x14 Tick on each; false |
| 53 | 0x1eeef0 | 288 | CEntity::PreTickAll(float, void*) | ent_main.cpp | MATCH | | a nonempty m_recycle sends its front (list+8 is the first node, +8 its value) to DoRecycleEntity; UpdateTargetList(false); slot 0x10 PreTick on each; false |
| 54 | 0x1ef010 | 548 | CEntity::RemoveAll() | ent_main.cpp | MATCH | | m_recycle cleared; entities popped from the front: the recycler's entity only counts down (at 0 entity, node (vptr +0x60) deleted and the three words zeroed), others deleted; then recycler entity / node deleted and zeroed, nextEntityId 0, m_target_inc / m_target_rem / m_target_add cleared in that order |
| 55 | 0x1ef240 | 492 | CEntity::DoRecycleEntity(CEntity*) | ent_main.cpp | MATCH | | remove from m_recycle; the inlined recycler make (node "recycler", new CEntity(1, node) 272, SetUpdateTargetList / SetIncludeInTargetList false) and count +1; slot 0x48 OnRecycleEntity on each, the entity's slot remembered (initially end); ReplaceTargetList(entity, placeholder); found: slot takes the placeholder (0x1ef3fc delay slot), entity deleted |
| 56 | 0x1ef430 | 272 | CEntity::CreateRecycler() | ent_main.cpp | MATCH | | the same inlined make and count +1; recycler_index -1: m_index = list size, appended, SetIncludeInTargetList(false); else m_index = recycler_index; returns the placeholder |
| 57 | 0x1ef540 | 224 | CEntity::RecycleEntity(unsigned int, CEntity*, bool) | ent_main.cpp | MATCH | | index < size; walk index nodes; slot non-NULL with byte m_type 1: slot = entity, SetIncludeInTargetList(include), UpdateTargetList(true). The ELF's bool return is unread by its one caller (0x1fcbd4 tests s2), so the port's void is equivalent |
| 74 | 0x2f8e90 | 540 | zdb::CTexture::CTexture(char const*) | ztex_main.cpp | MATCH | | m_name UNNAMED_TEX, m_palette 0, the reverse-miplist vector made (+0x5c), texel bits 16, width / height / gsaddr / selects / selectQwc / pal_offset / palID 0, the flag byte +0xf with only bit 4 (m_bilinear) set, m_AssetLib and htex_count 0; old name freed unless NULL / UNNAMED (line 305), _strdup (306) or UNNAMED; loadimage, TEX0, MIP1, MIP2 0. m_size, m_buffer, m_format untouched in both |
| 70 | 0x2f8860 | 252 | zdb::CTexList::Append(zdb::CTexture*, bool) | ztex_main.cpp | DEFECT-FIXED | B | the search (handle m_texture +0xc equal) as the ELF; a new handle is inserted at data + size (0x2f8938: appended); the port inserted it first. Changes the order of a library's texture list (GS upload / lookup order), no visible change known |
| 71 | 0x2f8960 | 200 | zdb::CTexList::GetHandle(char const*) | ztex_main.cpp | DEFECT-FIXED | C | the ELF skips a handle without a texture or whose texture's m_name (texture +0x14, 0x2f89c0) is NULL and compares that name; the port used the handle's own copy. Same text unless the texture is renamed after the handle is made |
| 72 | 0x2f8aa0 | 308 | zdb::CTexture::SetGifPtrs() | ztex_main.cpp | MATCH | | context bit (byte +0xf bit 7), NLOOP low 15 bits of the first qword; three scans of word 2 of each qword after the tag for 6 / 0x34 / 0x36 + ctx; TEX0 set or NULL, MIP1 / MIP2 only when found |
| 73 | 0x2f8c30 | 252 | zdb::CTexture::Compute64WordMemoryUsage() | ztex_main.cpp | MATCH | | width x height doubled for bits < 9 with 2 h < w and bits w < 2048; 32 / 24: palettized >> 2 else transp_1bit >> 1; 16: >> 2 or >> 1; 8 >> 2; 4 >> 4; rounded up to 64, >> 6 |
| 69 | 0x2f97e0 | 208 | zdb::CTexHandle::Create(zdb::CTexture*) | ztex_handle.cpp | DEFECT-FIXED | C | the inlined SetTexture's name records: _free / _strdup with "ztex_handle.cpp" lines 91 / 92 (0x2f9848 / 0x2f9864); the port used zfree (its own line) and libc strdup. Rest as the ELF: name / count / texture / libref 0, texture set, name copied, htex_count +1, count +1. The ELF leaves m_gsAddr (+0x8) unset; the port's value-initialised new zeroes it |
| 15 | 0x1db410 | 620 | zar::CZAR::Insert(zar::CKey*, void const*, int) | zar_search.cpp | MATCH | | NULL buffer or size <= 0 false; fseek(0, 2), -1 false; secured: _calloc(1, size, line 371), memcpy, the inlined Securify (m_bSecure tested again), fwrite of the copy, _free (375); else fwrite of the buffer; written == size; m_offset / m_size; padding size % m_data_padded (divu) with 0xaf secured else 'P' (movz 0x1db614), one byte per fwrite; true |
| 13 | 0x1db270 | 200 | zar::CZAR::Securify(void*, int) | zar_search.cpp | MATCH | | m_bSecure: every byte inverted (the ELF unrolls by 8) |
| 14 | 0x1db340 | 200 | zar::CZAR::Unsecurify(void*, int) | zar_search.cpp | MATCH | | the same inversion |
| 12 | 0x1db0a0 | 456 | zar::CZAR::Fetch(zar::CKey*, void*, int, unsigned int) | zar_search.cpp | MATCH | | file open, OpenKey(key); size nonzero: fseek(offset, 0) == offset; m_size >= size (slt): fread == size, then the inlined Unsecurify whatever fread gave; a short key keeps the fseek result (true); CloseKey; the fourth argument unread in both |
| 23 | 0x1dc2d0 | 372 | zar::CKey::Write(zar::CZAR*) | zar_search.cpp | MATCH | | name (+0xc), offset (+0x14), size (+0x10), child count: each word secured, written, unsecured in place (the port secures a copy: the same bytes, members unchanged); children depth first; true |
| 11 | 0x1daf80 | 276 | zar::CZAR::FetchLIP(zar::CKey*, void**) | zar_search.cpp | MATCH | | dynamic_cast to CBufferIO first; open / OpenKey; size nonzero: fseek == offset, then slot 0x28 fread(m_size, buf) != 0; CloseKey |
| 16 | 0x1db880 | 400 | zar::CZAR::FetchAll(int (*)(zar::CZAR&, char const*, void*, int, void*), void*) | zar_search.cpp | MATCH | | per key of the open key: open / OpenKey, fseek != -1, FetchLIP into a zeroed pointer, callback(this, name, data, size, context), valid 0 < result <= size; CloseKey; counted; count != 0 |
| 17 | 0x1dba10 | 284 | zar::CZAR::Fetch(char const*, int (*)(zar::CZAR&, int, void*), void*) | zar_search.cpp | MATCH | | NULL open key false; FindKey; open / OpenKey; fseek != -1; hackStr = name; callback(this, size, buf), 0 < result <= size; CloseKey |
| 18 | 0x1dbb30 | 316 | zar::CZAR::Fetch(char const*, void*, int) | zar_search.cpp | MATCH | | NULL open key false; FindKey (no NULL test in either); then the same body as #12 with an Unsecurify call |
| 19 | 0x1dbc70 | 352 | zar::CZAR::FetchString(char const*, char*, int) | zar_search.cpp | MATCH | | NULL open key / key 0; size < m_size 0; the #18 body with m_size as the length; m_size on success else 0 |
| 20 | 0x1dbdd0 | 248 | zar::CZAR::Fetch(char const*, char**) | zar_search.cpp | MATCH | | file open; GetSize > 0; _calloc(size + 1, 1, line 161) into *buf; NULL open key false; Fetch(FindKey(name), str, size, 0) |
| 21 | 0x1dc0e0 | 232 | zar::CKey::FindKey(char const*) | zar_search.cpp | MATCH | | first child with size != -1 and strcasecmp(name, child name) 0; else NULL |
| 22 | 0x1dc1d0 | 252 | zar::CKey::Read(zar::CZAR*, CIO*, int) | zar_search.cpp | MATCH | | 16-byte record; not the root: name = word 0 + strbase, offset word 1, size word 2; count children: NewKey(NULL), Read, appended; true |
| 5 | 0x1d8f70 | 484 | zar::CZAR::CreateKey(char const*) | zar_main.cpp | MATCH | | file open; NewKey's storage rule inlined (read mode: by value in m_key_buffer, CreateString name or the empty key; else new CKey(CreateString(name))); parent = m_keys empty ? m_root : front; InsertKey; a key is pushed to the front of m_keys |
| 1 | 0x1d7ff0 | 316 | zar::CZAR::NewKey(char const*) | zar_main.cpp | MATCH | | mode & 1: m_key_buffer.push_back of CKey(CreateString(name)) or CKey(), the last element returned; else new CKey(CreateString(name)) (24) |
| 2 | 0x1d8480 | 380 | _countKeys(zar::CKey*) | zar_main.cpp | MATCH | | 1 + per child (1 + per grandchild (1 + the recursive count of each great-grandchild)), the ELF's three unrolled levels |
| 3 | 0x1d8600 | 308 | zar::CKey::fixupKey(CSTable*, void*) | zar_main.cpp | MATCH | | the key's name through FindString, each child's name, then fixupKey on every grandchild |
| 4 | 0x1d8e30 | 204 | zar::CZAR::OpenKey(char const*) | zar_main.cpp | MATCH | | file open: FindKey in the front open key or the root; found keys pushed to the front of m_keys |
| 6 | 0x1d9200 | 640 | zar::CZAR::Open(char const*, int, unsigned int, unsigned int) | zar_main.cpp | MATCH | | NULL name false; a CFileIO made when there is no stream (both pointers); slot 8 Open(name, mode); the inlined SetFilename (free line 89, the same pointer kept, DEFAULT for NULL / DEFAULT, _strdup line 96); m_data_padded; ReadDirectory(version, mode); success sets appversion, failure runs the inlined Close (0x1d9314) |
| 7 | 0x1d9560 | 288 | zar::CZAR::ReOpen(int, unsigned int) | zar_main.cpp | MATCH | | open stream: true; m_filename NULL false; CFileIO made if none; Open(filename, mode); SetFilename, padded 16, ReadDirectory; failure Close and false, else appversion |
| 8 | 0x1d97a0 | 328 | zar::CZAR::Close() | zar_main.cpp | MATCH | | open, mode & 6, open again and m_modified: WriteDirectory, m_modified 0; an owned stream closed, deleted and both pointers zeroed, else the stream closed; m_key_buffer cleared and swapped empty; the root's children erased; m_stable->Destroy() |
| 9 | 0x1d99a0 | 684 | zar::CZAR::~CZAR() | zar_main.cpp | MATCH | | the inlined Close, m_stable deleted, m_key_buffer cleared / swapped, the inlined SetFilename(DEFAULT), m_filename DELETED, m_root deleted and zeroed |
| 10 | 0x1d9c50 | 444 | zar::CZAR::CZAR(char const*, CIO*) | zar_main.cpp | MATCH | | m_pFileAlloc / m_databuffer / m_root / m_stable / m_filename 0, compress / secure 0, m_tail zeroed (96 bytes) with version 0x20001, new CSTable(0, 1024), the inlined SetFilename(name), a CFileIO for a NULL io (owned), m_pFile, m_data_padded 16, m_root = new CKey(DEFAULT). The port's memset of 92 is GCC splitting the version store |
| 30 | 0x1dfd00 | 428 | CZBodyAnimBlend::SetBlendAnims(CBody*, CActiveAnimList*) | body.cpp | MATCH | | each anim removed, its overlays cleared and put back, it cleared (inline) and put back (the port's CActiveAnimPool::PutBack clears then puts back: the same); the list's anims added; Normalize; flag 1 cleared, set (and the scan stopped) at the first anim with GetCallbackIndex(0) > 0 |
| 27 | 0x1df920 | 272 | CZBodyAnimBlend::Clear() | body.cpp | MATCH | | quitT, tfrac, action node, result parent, flags, ctrl, state 0, animType -1, the anim list cleared, the callback's three words, homing blend 0 and its five vectors zero |
| 40 | 0x1e2350 | 644 | CBody::PopBlend() | body.cpp | MATCH | | the snapshot under !(interp1 <= 0); looped flag 0x40 and tfrac of the old top; its first anim; every anim's flag 0x40 cleared, overlays and anim back to the pool; Clear, back to the blend pool, Pop; NULL new top returns NULL; interp1 / interp2 = the new top's first anim's blend time; Reset when it plays the old first anim; m_state; the old time when both are looped |
| 24 | 0x1df120 | 472 | CZBodyAnimCallbackList::AddCallback(char const*, float) | body.cpp | MATCH | | an empty list first gets "null" (func 0, valid 1, time 0); the index of the first entry with time == (c.eq) and strcmp 0; else a new entry appended, size - 1 |
| 25 | 0x1df480 | 288 | CZBodyAnimCallbackList::~CZBodyAnimCallbackList() | body.cpp | MATCH | | the inlined Clear: this list's entries deleted (string first), the global BodyAnimCallbackList swapped empty (quirk kept in Clear) |
| 26 | 0x1df610 | 604 | CBody::Destroy() | body.cpp | MATCH | | the overlay's anim cleared and put back, the overlay's words zeroed; Top read once (quirk kept); PopBlend until the stack's top index is -1; overlay deleted; body anims (slot 8 deleting dtor) and both part vectors deleted with slots zeroed and sizes 0; blend pool, blend stack (array first) and anim pool deleted and zeroed |
| 35 | 0x1e08d0 | 584 | CZBodyAnimBlend::CallbackTick(CBody*, float, float) | body.cpp | MATCH | | the blend callback when IsTriggerTime(tfrac, from, to), then cleared; flag 1: per anim the four index bytes +0x20..+0x23, the slot loop ending at an index <= 0; entry by bounds-checked index, IsTriggerTime(time); GetAnim(name, NULL) once (valid cleared); GetRootPart (CBody slot 0x10), its node or the node's parent; ActivateArg(anim, 1, 2, node, 0) |
| 43 | 0x1e34b0 | 228 | CBody::NewBodyPart(zdb::CNode*, CZBodyPart*) | body.cpp | MATCH | | NullNode (slot 0xc); a node: BodyId(name), negative NULL; new CZBodyPart(node) (80, the inlined ctor: id -1, blendme 1, node, parent 0, pos zero, rot identity); parent; id |
| 42 | 0x1e32d0 | 272 | CBody::AttachAuxNode(zdb::CNode*, CZBodyPart*, CPnt3D const*, CPnt3D const*) | body.cpp | MATCH | | QFromRot; new part; parent; parent node slot 0x18 AddChild(node); part node; pushed to the aux parts; pos, the quaternion; SetPosition, SetRotation; the part |
| 44 | 0x1e35a0 | 416 | CBody::BodySetup(zdb::CNode*, CZBodyPart*) | body.cpp | MATCH | | the inlined NewBodyPart for the node (NULL when its id is negative); stored by id; per child NewBodyPart(child, part), stored, BodySetup on each grandchild |
| 36 | 0x1e1700 | 332 | CBlendOverlay::Trigger(CBody*, bool) | body.cpp | DEFECT-FIXED | C | the snapshot test is !(interp1 <= 0) (c.le / bc1t, 0x1e176c), the port had interp1 > 0: differs only for a NaN (the lead from audit-large-rest). Rest as the ELF: no anim false; state 0: -1 / 1, snapshot, interp1 / interp2 = blend time; true |
| 37 | 0x1e1850 | 304 | CBlendOverlay::IsTriggerTime(float, float, bool) | body.cpp | DEFECT-FIXED | C | NaN forms: the backward wrap is (to - 1) <= t && t <= from (c.le, 0x1e18cc; the port had !(t < to - 1 or from < t)) and the forward wrap is taken on to < from (c.lt / bc1t, 0x1e1900; the port tested from <= to). -4 always true; bounds and the wrap by 1 as the ELF |
| 32 | 0x1e0170 | 680 | CZBodyAnimBlend::Synch(CBody*) | body.cpp | MATCH | | v = dfrac + tfrac; cycling: wrapped by 1 (!(v <= 1), v < 0), else !(v <= quitT) quitT, v < 0 zero; the anim and each overlay wrap v again, tfrac, script_wt = w x frames (s16), floorf, a = fptosi, b = a + 1, script_wt - key |
| 41 | 0x1e2a00 | 248 | CBody::SmoothAnims(float) | body.cpp | MATCH | | rest = 1 - w; per part with blendme: saved pos x w, pos x rest, pos + saved, Slerp(rot, saved rot, w) into rot |
| 34 | 0x1e0730 | 416 | CZBodyAnimBlend::IsTriggerTime(float, float, float) | body.cpp | DEFECT-FIXED | C | the forward wrap is taken on to < from (c.lt / bc1t, 0x1e0848); the port tested from <= to (NaN only). from == to false; backwards from flag 0x20, or for a cycling blend the first anim's tScale < 0; bounds and the wrap by quitT as the ELF |
| 38 | 0x1e1bf0 | 296 | CZBodyAnim::SetMultiplier(bool) | body.cpp | DEFECT-FIXED | C | the distance test is !(distance <= 0.2) (c.le / bc1t, 0x1e1c78; word 0x3e4ccccd equal), the port had distance > 0.2 (NaN only). Looped: tf / distance or 100 tf / distance, applied as SetTimeScale(m x (tScale / old m)), stored (1 when short); not looped: m 1, SetTimeScale(-1 for tScale < 0 else 1) |
| 39 | 0x1e1e20 | 292 | CZBodyAnim::Update(float, float) | body.cpp | MATCH | | speed < 0: 0 and flag 0x200, else cleared; looped scale speed / 100 (1 when it equals 0); thr_scale; looped without 0x200 SetLoopTime(tf / time), else SetLoopTime(time); SetMultiplier(false) |
| 45 | 0x1e3740 | 260 | CBody::CBody() | body.cpp | MATCH | | take_snapshot 1, interp1 / interp2 0, the three vectors, maxid -1, blend pool and stack 0; new CBlendOverlay (28) all zero; m_state and the anim pool left as the ELF leaves them |
| 33 | 0x1e0420 | 504 | CZBodyAnimBlend::Propagate(float, bool) | body.cpp | DEFECT-FIXED | C | the playback test is !(playback <= 0) (c.le / bc1t, 0x1e047c), the port had playback > 0 (NaN only). Rest as the ELF: size 0 returns 0; dT scaled cumulatively (quirk kept); loop (n - 1) / n unless looped or !(n > 1); sum += dT (wt tScale) / (tf loop); t = sum + tfrac; wrap or clamp; stored when apply |
| 28 | 0x1dfb20 | 224 | CZBodyAnimBlend::AddOverlay(ACTIVE_ANIM*, ACTIVE_ANIM*, float) | body.cpp | MATCH | | overlay linked, its overlay 0, weight, playback; a reversed blend (0x20) sets the anim's 0x80; callback index > 0 sets flag 1; the overlay anim's 0x40 copied from the anim; tScale copied |
| 29 | 0x1dfc00 | 244 | CZBodyAnimBlend::Normalize() | body.cpp | MATCH | | pool size 0 returns (quirk kept); sum of weights; _close_enough(sum, 1, 1e-5) (gp words 0x3f800000 / 0x3727c5ac) returns; sum <= 1e-5 returns; weights x (1 / sum) |
| 31 | 0x1dffa0 | 448 | CZBodyAnimBlend::GetVelocity(CPnt3D*) | body.cpp | DEFECT-FIXED | C | the playback test is !(playback <= 0) (c.le / bc1t, 0x1e0078), the port had playback > 0 (NaN only). Rest as the ELF: vel zero; per anim the base part's object (bounds-checked, NULL otherwise), GetVelRaw(anim, a, b); non-cycling with playback != 1: x (1 / playback); mirrored anim (0x40) negates x; vel += wt v |
| 47 | 0x1f1e70 | 260 | CEntity::ComputeNextPosition(float) | ent_entity.cpp | MATCH | | velM.y kept, velW.y / velM.y zeroed; next quat = quat; velR x (0.5 dT); Exp; Mul by the next quat, Normalize into it; Apply(velM) into next_velw; x dT; node row 3 + d into next matrix row 3; ToMatrix; velocities' y restored |
| 77 | 0x2fa270 | 332 | zdb::CTexManager::DestroyBuffers(zdb::CTexManager&, bool) | ztex_manager.cpp | MATCH | | keep 0 for all else 1; while keep < size: the last buffer's inlined destructor (name _free line 80, both lists and the chain buffer cleared and freed) and delete, size - 1; every TexPhase row's three words 0; the ELF's return 1 is unread (void kept) |
| 79 | 0x2fb190 | 656 | zdb::CTexManager::doAddBuffer(char const*, float, float) | ztex_manager.cpp | MATCH | | new CGSTexBuffer (64; the inlined ctor: overflow check 1, addresses, lib, chain, name 0); name freed (93), _strdup (94) or NULL; first = fptoui(base + start range), last = fptoui(base + end range - 1) with unsigned-to-float base and range; a changed range resets next / start / end / chain; appended (grow by one); size - 1. fptoui vs GCC (u32): never negative here (texture base 0x2bc0, start / end >= 0) |
| 88 | 0x2fc990 | 216 | zdb::CGSTexBuffer::~CGSTexBuffer() | ztex_manager.cpp | MATCH | | name freed (line 80) and zeroed, both list sizes 0, the chain buffer cleared, member destructors |
| 86 | 0x2fc3b0 | 416 | zdb::CGSTexBuffer::SetDynTexList(zdb::CDynTexList*) | ztex_manager.cpp | MATCH | | both list sizes 0; a list: each handle through Add(handle, true), each palette not found pushed (grow by one); chain 0 in both cases |
| 78 | 0x2fb050 | 308 | zdb::CTexManager::doDelBuffer(zdb::CGSTexBuffer*) | ztex_manager.cpp | MATCH | | remove of the pointer (find then remove_copy) and erase; the inlined destructor and delete for a non-NULL buffer |
| 84 | 0x2fc100 | 340 | zdb::CGSTexBuffer::Setup(float, float) | ztex_manager.cpp | MATCH | | the doAddBuffer range formula (fptoui, never negative here), the reset on a change; returns m_endAddress |
| 82 | 0x2fb840 | 340 | refLoadImage(_word128*, unsigned int, unsigned int, void*, unsigned int, unsigned int, unsigned int) | ztex_manager.cpp | MATCH | | DBW 1 for width <= 64 else width >> 6; qwc = size >> 4 split at 0x8000 (rest qwc - 0x7fff); CNT 6, A+D x4 (BITBLTBUF psm / gsaddr / bw / psm, TRXPOS 0, TRXREG w / h, TRXDIR 0), IMAGE EOP tag, REF qwc -> buffer; the rest as CNT 1 + REF at buffer + 0x80000; returns past the last tag |
| 87 | 0x2fc610 | 324 | zdb::CDynTexList::Add(zdb::CTexHandle*, bool) | ztex_manager.cpp | MATCH | | check and GetHandle(texture) found: return; the handle appended (the ELF grows by one; capacity only); the texture's palette (+0x1c), unless NULL or (check) found, appended |
| 85 | 0x2fc260 | 332 | zdb::CGSTexBuffer::Add(zdb::CTexList*, bool) | ztex_manager.cpp | MATCH | | count read once; per handle Add(handle, check), chain 0; its palette: unchecked or not found pushed (grow by one); chain 0 |
| 75 | 0x2f9d00 | 544 | zdb::CTexture::MIPUpdateTextureSelects(unsigned int, unsigned int) | ztex_manager.cpp | MATCH | | for MIP1 then MIP2: TBP1 (bits 0-13, halfword in the ELF), TBP2 (20-33, mask 0xfffffffc000fffff) and TBP3 (40-53, mask 0xffc000ffffffffff) equal to old get the new block, through the cached word and its | 0x20000000 alias; each test reads the updated word |
| 76 | 0x2f9f20 | 524 | zdb::CGSTexBuffer::UpdateTextureSelects() | ztex_manager.cpp | MATCH | | next = start; palettes get next, + size / 256; per handle: old gsAddr kept, new set; TBP0 patched when different (both aliases); each reverse-mip parent's MIPUpdateTextureSelects(old, new); a palette's CBP (bits 37-50) written; next = addr + gsWords |
| 80 | 0x2fb420 | 372 | zdb::CGSTexBuffer::Add(zdb::CAssetLib*, bool) | ztex_manager.cpp | MATCH | | m_assetLib; each texture handle Add(h, check), chain 0; a copy of the palette list, each unchecked or not found pushed, chain 0 |
| 81 | 0x2fb610 | 556 | zdb::CGSTexBuffer::Load(bool) | ztex_manager.cpp | MATCH | | both lists empty: NULL; upload: Hookup(lib); no chain: (textures + palettes) x 11 + 3 qwords, cleared and resized, MakeChain, chain = its return (the start); else palettes then textures re-laid from start (size / 256, gsWords); upload: UpdateTextureSelects, DmaSync / Send / Sync on zSys+0x8; the chain |
| 83 | 0x2fb9a0 | 496 | zdb::CGSTexBuffer::MakeChain(uint16*, int) | ztex_manager.cpp | MATCH | | next = start; palettes: overflow skip when next + blocks >= end, gsaddr, next += blocks, with a buffer refLoadImage(format byte +6, size, 16, 16); textures (NULL skipped): the same with gsWords and (format +0x28, size, width, height); END 2 + A+D TEXFLUSH; FlushCache(0); the ELF returns the start, which the port's Load takes itself |
| 60 | 0x1f0930 | 548 | CEntity::ReplaceTargetList(CEntity*, CEntity*) | ent_target.cpp | MATCH | | entities of type 1 and the old entity skipped; each target on old: new's GetPosW - owner's GetPosW (slot 0xc) or (0, 0, 1e6) (0x49742400); distSq (x x + y y) + z z (adda / madd); d_computed 0; a changed entity: m_ent, aware 0, the four flags 0, diHandle 0 |
| 58 | 0x1ef980 | 328 | CTarget::Update(CEntity*, CEntity*) | ent_target.cpp | MATCH | | the same vector / distance / reset body for one target; returns distSq |
| 59 | 0x1f0220 | 348 | CEntity::RefreshAwareCounters() | ent_target.cpp | MATCH | | per entity: counter 0 (the ELF's in-loop clearing kept), type byte 1 or either flag bit of byte +0xdd clear skips; each visible target (byte +0x24 bit 2) adds 1 to its entity's counter |
| 61 | 0x1f0b60 | 408 | CEntity::SetIncludeInTargetList(bool) | ent_target.cpp | MATCH | | unchanged (byte +0xdd bit 2): return; include: removed from m_target_rem, appended to m_target_add unless in m_target_inc; else appended to m_target_rem and removed from m_target_add; the bit set |
| 46 | 0x1dc520 | 380 | CBody::PartInSpace(CZBodyPart*, CPnt3D const*, CPnt3D*, CQuat*) const | zbody_main.cpp | MATCH | | NULL part returns; p = part rot Apply(local) or zero; q = part rot when rot is asked, else identity; up the chain: (p + part pos) through the parent's rot Apply, q = parent rot Mul q; pos = p + top part's pos; rot = Normalize(q) |
| 89 | 0x2f90e0 | 440 | zdb::CTexture::Read(zdb::CSaveLoad&) | ztex_read.cpp | MATCH | | FindKey("texdat"), FetchLIP: 16 bytes of params, _malloc(96, line 469) load image, buffer at +0x18 + skip0, select block after size + skip1, GetTextureSelectBlock_ver2(selectQwc, &gifSelect, &dmaRef, &dmaRefVu), gsWords, the back-pointer in word 3, SetGifPtrs; format 0x14 / 0x13 / 1 / 0, else palettized 0x13 or 2; palID = TEX0 bits 37-50 unguarded |
| 90 | 0x2f9510 | 232 | zdb::CTexture::LoadGS(unsigned int, char*, void*, unsigned int, unsigned int, unsigned int) | ztex_read.cpp | MATCH | | buffer, SetName, format, width, height, gsaddr & 0x3fff; the block count; bit 31 or below the base: SetupSpecialTextures; buffer and m_freeAfterLoad: DmaSync, _free (line 140), 0; the count |
| 68 | 0x24d4a0 | 396 | CPickup::Close(bool) | pickup_main.cpp | MATCH | | Destroy the list's front until empty; GetMPBomb (searches the emptied list, quirk kept): Destroy, else the bomb node out of its parent (slot 0x1c), DeleteTextureAssetCharacter(2, node), CNode::Delete, 0; all: each pooled pickup's bit words freed (the inlined CBits dtor, decided in audit-unmarked-a2) and deleted, slot 0, the pool erased; m_isOpen 0 |
| 67 | 0x24d200 | 544 | CPickup::NetworkCreate(unsigned char, CPickup::PU_TYPE, zdb::CNode*, void*) | pickup_main.cpp | DEFECT-FIXED | C | Create's body inlined (the same steps as #66, its memset through CBits::GetWordCount = (bits >> 5) + 1, equal); net id = entity << 8 | kept earlier; guard removed 2026-11-20: Create's NULL (closed) takes the net id. Earlier: m_nextNetPickupId, the index moved on, then past every IsNetIdUsed(entity, index). Kept: while closed the port returns NULL where the ELF writes the id through NULL and runs the index loop (reason in the code) |
| 66 | 0x24cfe0 | 412 | CPickup::Create(CPickup::PU_TYPE, zdb::CNode*, void*) | pickup_main.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: a failed allocation is written through. Earlier: closed: NULL; the pool's first (taken off) or new CPickup (28; secondary bit 0, bits 0 / NULL, Resize(bit_count)); visible 0, type & 0x7f, node, data, bit words zeroed ((bits >> 5) + 1 words) or count 0, locked 0, id = nextPickupId++, netid 0, appended. Kept: the port's NULL test after a failed allocation (reason in the code) |
| 62 | 0x24c4c0 | 332 | CPickup::CleanupAmmoPickup(CPickup*) | pickup_main.cpp | MATCH | | ammo (type 9): entries with neither weapon nor ammo erased from the three vectors (the ELF keeps the erase results as its iterators: the same index walk), none left: Destroy; weapon (8) with NULL data: Destroy |
| 63 | 0x24c6c0 | 212 | CPickup::IsNetIdUsed(unsigned char, unsigned char) | pickup_main.cpp | MATCH | | any listed pickup whose net id high byte is the entity and low byte the index |
| 64 | 0x24c840 | 448 | CPickup::GetClosest(CPnt3D const*, float, CPickup::PU_TYPE, CPickup**) | pickup_main.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: the node's position is read without a NULL test. Earlier: empty list NULL; best = second = 1 + r r; type 0 or equal; d = (x x + y y) + z z of node row 3 - pos; an out pointer and a secondary weapon (type 8, byte +9 bit 0): d < second (c.lt) goes there; else d < best. Kept: the port skips a pickup without a node (the ELF subtracts from address 0; reason in the code) |
| 65 | 0x24ca00 | 312 | CPickup::GetNext(std::list<CPickup*, std::allocator<CPickup*>>::generic_iterator<0>&, CPnt3D const*, float, CPickup::PU_TYPE) | pickup_main.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: the node's position is read without a NULL test. Earlier: empty list NULL; range r r; from the iterator: type 0 or equal, d < range (c.lt) returns the pickup with the iterator past it, else on; NULL at the end. Kept: the same NULL-node guard as #64 (reason in the code) |
