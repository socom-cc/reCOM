# Compiler copies among the stage-4 undecided functions

These 10 need no source placement: the compiler generated each copy inside the file that used it,
from code in a header. They are recorded with their source home so the amendment covers them.

## Inline in their class headers
- 0x231d80  zdb::CVisData::~CVisData()  -> zVisual/zvis.h (inline in CVisData)
- 0x3030a0  zdb::CTextureRelocMgr::AddToBatch(zdb::CTexHandle *) const  -> zTexture/ztex.h
- 0x3030b0  zdb::CTextureRelocMgr::EndBatchReloc() const  -> zTexture/ztex.h
- 0x3030c0  zdb::CTextureRelocMgr::StartBatchReloc() const  -> zTexture/ztex.h
- 0x3030d0  zdb::CTextureRelocMgr::ClearAll()  -> zTexture/ztex.h

## Standard-library template instantiations (MSL headers; provider code, no game source)
- 0x1daf70  std::__list_deleter<const void *, std::allocator<const void *> >::end() const  (<list>)
- 0x217560  std::vector<zdb::CTexPalette *>::~vector()  (<vector>)
- 0x2175f0  std::vector<zdb::CTexHandle *>::~vector()  (<vector>)
- 0x224740  std::remove_copy<zdb::CNode **, zdb::CNode **, const zdb::CNode *>(...)  (<algorithm>)
- 0x2fe940  std::list<C2D *>::list(const std::list<C2D *> &)  (<list>)
