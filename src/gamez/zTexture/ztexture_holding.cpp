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

/* @socom-skeleton body ClearAll__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:18 */
namespace zdb {
void CBatchRelocator::ClearAll()
	{
		/* 0x2f9ab0: empty buffer 0 (lists, chain packet) and drop its name */
		CGSTexBuffer* buffer = reinterpret_cast<CGSTexBuffer*>(CTexManager::m_texmanager[0]);
		buffer->m_dyntex_list.m_tex_list.clear();
		buffer->m_dyntex_list.m_pal_list.clear();
		buffer->m_pktbuf.clear();

		if (buffer->m_name != NULL)
			_free(buffer->m_name, "ztex_manager.cpp", 88);

		buffer->m_name = NULL;
	}
}

/* @socom-skeleton body EndBatchReloc__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:23 */
namespace zdb {
void CBatchRelocator::EndBatchReloc() const /* port: the ELF has only EndBatchReloc__Q23zdb15CBatchRelocatorCFv */
	{
		/* 0x2f9b70: lay out and upload buffer 0's batch (PATH3, synchronously): a new
		 * chain when the batch changed, else the same chain at re-laid addresses */
		CGSTexBuffer* buffer = reinterpret_cast<CGSTexBuffer*>(CTexManager::m_texmanager[0]);

		if (buffer->m_dyntex_list.m_tex_list.empty() && buffer->m_dyntex_list.m_pal_list.empty())
			return;

		buffer->Hookup(buffer->m_assetLib);

		if (buffer->m_chainp == NULL)
		{
			u32 qwc = (buffer->m_dyntex_list.m_tex_list.size() + buffer->m_dyntex_list.m_pal_list.size()) * 11 + 3;
			buffer->m_pktbuf.clear();
			buffer->m_pktbuf.resize(qwc); /* port: unproven fill value - 0x2f9c18 passes the qword at 0x43a850 */
			buffer->MakeChain(reinterpret_cast<unsigned __int128*>(buffer->m_pktbuf.data()), qwc);
			buffer->m_chainp = reinterpret_cast<s64*>(buffer->m_pktbuf.data());
		}
		else
		{
			buffer->RelocateAll();
		}

		buffer->UpdateTextureSelects();
		void* chain = buffer->m_chainp;
		sceDmaSync(zSys.DmaToGif, 0, 0);
		sceDmaSend(zSys.DmaToGif, chain);
		sceDmaSync(zSys.DmaToGif, 0, 0);
	}
}

/* @socom-skeleton body StartBatchReloc__Q23zdb15CBatchRelocatorFv */
/* held from src/gamez/zTexture/ztex_manager.cpp:28 */
namespace zdb {
void CBatchRelocator::StartBatchReloc() const /* port: the ELF has only StartBatchReloc__Q23zdb15CBatchRelocatorCFv */
	{
		/* 0x2f9ca0: buffer 0 starts an empty batch */
		CGSTexBuffer* buffer = reinterpret_cast<CGSTexBuffer*>(CTexManager::m_texmanager[0]);
		buffer->m_dyntex_list.m_tex_list.clear();
		buffer->m_dyntex_list.m_pal_list.clear();
		buffer->m_chainp = NULL;
	}
}
