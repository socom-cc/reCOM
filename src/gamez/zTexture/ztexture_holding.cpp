/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

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

/* @socom-skeleton body Init__Q23zdb8CTextureFv */
/* held from src/gamez/zTexture/ztex_main.cpp:57 */
namespace zdb {
void CTexture::Init()
	{
		m_baseAddress = zVid.textureBaseAddr;
		m_endAddress = zVid.textureEndAddr;
		m_startAddress = zVid.textureBaseAddr + 0x200;
	}
}

/* @socom-skeleton body AddToBatch__Q23zdb15CBatchRelocatorCFPQ23zdb10CTexHandle */
/* held from src/gamez/zTexture/ztex_manager.cpp:12 */
namespace zdb {
void CBatchRelocator::AddToBatch(zdb::CTexHandle* handle) const
	{
		CDynTexList* dynTexList = CTexManager::m_texmanager->front();
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
void CBatchRelocator::EndBatchReloc()
	{

	}
}

/* @socom-skeleton body StartBatchReloc__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:28 */
namespace zdb {
void CBatchRelocator::StartBatchReloc()
	{

	}
}
