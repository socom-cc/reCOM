/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zTexture/ztex.h"
#include "gamez/zVideo/zvid.h"

/* @socom-skeleton body m_baseAddress__Q23zdb8CTexture */
/* held from src/gamez/zTexture/ztex_main.cpp:10 */
namespace zdb {
u32 CTexture::m_baseAddress = 0;
}

/* @socom-skeleton body m_endAddress__Q23zdb8CTexture */
/* held from src/gamez/zTexture/ztex_main.cpp:11 */
namespace zdb {
u32 CTexture::m_endAddress = 0;
}

/* @socom-skeleton body m_startAddress__Q23zdb8CTexture */
/* held from src/gamez/zTexture/ztex_main.cpp:12 */
namespace zdb {
u32 CTexture::m_startAddress = 0;
}

/* @socom-skeleton body AddToBatch__Q23zdb15CBatchRelocatorCFPQ23zdb10CTexHandle */
/* held from src/gamez/zTexture/ztex_manager.cpp:12 */
namespace zdb {
void CBatchRelocator::AddToBatch(zdb::CTexHandle* handle) const
	{
		CDynTexList* dynTexList = CTexManager::m_texmanager[0]; /* port: m_texmanager is an object; 0x2f9b38 calls operator[](0) */
		dynTexList->Add(handle, true);
	}
}

/* @socom-skeleton body ClearAll__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:18 */
namespace zdb {
void CBatchRelocator::ClearAll()
	{

	}
}

/* @socom-skeleton body EndBatchReloc__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:23 */
namespace zdb {
void CBatchRelocator::EndBatchReloc() const /* port: the ELF has only EndBatchReloc__Q23zdb15CBatchRelocatorCFv */
	{

	}
}

/* @socom-skeleton body StartBatchReloc__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:28 */
namespace zdb {
void CBatchRelocator::StartBatchReloc() const /* port: the ELF has only StartBatchReloc__Q23zdb15CBatchRelocatorCFv */
	{

	}
}
