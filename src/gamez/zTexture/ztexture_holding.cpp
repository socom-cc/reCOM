/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zTexture/ztex.h"
#include "gamez/zVideo/zvid.h"
#include "gamez/zSystem/zsys.h" /* zSys (EndBatchReloc) */
#include <libdma.h> /* sceDmaSend, sceDmaSync */

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
		/* 0x2f9b20: buffer 0 lists the handle (once) and its chain is rebuilt at the end */
		CGSTexBuffer* buffer = reinterpret_cast<CGSTexBuffer*>(CTexManager::m_texmanager[0]); /* port: the ELF vector holds CGSTexBuffer * (see doAddBuffer) */
		buffer->m_dyntex_list.Add(handle, true);
		buffer->m_chainp = NULL;
	}
}
