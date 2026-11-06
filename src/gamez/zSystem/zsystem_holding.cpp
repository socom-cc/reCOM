/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <stdlib.h>
#include "gamez/zSystem/zsys.h"
#include "gamez/zSystem/zsys_bench.h"

/* @socom-skeleton body countNodes__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:3 */
u32 CBench::countNodes = 0;

/* @socom-skeleton body countRenderNodes__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:4 */
u32 CBench::countRenderNodes = 0;

/* @socom-skeleton body countAlphaNodes__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:5 */
u32 CBench::countAlphaNodes = 0;

/* @socom-skeleton body countClutterNodes__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:6 */
u32 CBench::countClutterNodes = 0;

/* @socom-skeleton body countVisuals__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:7 */
u32 CBench::countVisuals = 0;

/* @socom-skeleton body countAlphaVisuals__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:8 */
u32 CBench::countAlphaVisuals = 0;

/* @socom-skeleton body drawTimeX__6CBench */
/* held from src/gamez/zSystem/zsys_bench.cpp:9 */
f32 CBench::drawTimeX[10];

/* @socom-skeleton body zSys */
/* held from src/gamez/zSystem/zsys_main.cpp:3 */
_zsys_public zSys;

/* @socom-skeleton body postinit */
/* held from src/gamez/zSystem/zsys_main.cpp:4 */
/* port: not in the ELF (the binary has the LOCAL postinited in zsys_init.cpp); nothing uses it */
#if 0
bool postinit = false;
#endif

/* @socom-skeleton body _HeapSize */
/* held from src/gamez/zSystem/zsys_memory.cpp:11 */
size_t __HeapSize = 0; /* port: __HeapSize (C name; zsys_FullAllocAndFree stores it at 0x2f4964) */

/* @socom-skeleton body __malloc__FUiPCci */
/* held from src/gamez/zSystem/zsys_memory.cpp:88 */
/* port: duplicate of the gamez/zSystem/zsys_memory.cpp stub _malloc__FUiPCci (this body is its candidate) */
#if 0
void* __malloc(size_t size, const char* file, int line)
{
	void* p = malloc(size);
	zVid_Assert(size == 0 || p != NULL, INT_MAX, __FILE__, __LINE__);
	return p;
}
#endif

/* @socom-skeleton body __calloc__FUiUiPCci */
/* held from src/gamez/zSystem/zsys_memory.cpp:95 */
/* port: duplicate of the gamez/zSystem/zsys_memory.cpp stub _calloc__FUiUiPCci (this body is its candidate) */
#if 0
void* __calloc(size_t num, size_t size, const char* file, int line)
{
	size_t calc_size = num * size;
	void* p = malloc(calc_size);

	if (p == NULL)
	{
		zVid_Assert(false, INT_MAX, __FILE__, __LINE__);
		return NULL;
	}

	memset(p, 0, calc_size);
	zVid_Assert(calc_size == 0 || p != NULL, INT_MAX, __FILE__, __LINE__);
	return p;
}
#endif

/* @socom-skeleton body __realloc__FPvUiPCci */
/* held from src/gamez/zSystem/zsys_memory.cpp:111 */
/* port: duplicate of the gamez/zSystem/zsys_memory.cpp stub _realloc__FPvUiPCci (this body is its candidate) */
#if 0
void* __realloc(void* ptr, size_t new_size, const char* file, int line)
{
	void* p = realloc(ptr, new_size);
	zVid_Assert(new_size == 0 || p != NULL, INT_MAX, __FILE__, __LINE__);
	return p;
}
#endif

/* @socom-skeleton body __memalign__FUiUiPCci */
/* held from src/gamez/zSystem/zsys_memory.cpp:118 */
/* port: duplicate of the gamez/zSystem/zsys_memory.cpp stub _memalign__FUiUiPCci (this body is its candidate) */
#if 0
void* __memalign(size_t alignment, size_t size, const char* file, int line)
{
	void* p = _aligned_malloc(size, alignment);
	zVid_Assert(alignment == 0 || p != NULL, INT_MAX, __FILE__, __LINE__);
	return p;
}
#endif

/* @socom-skeleton body __strdup__FPCcPCci */
/* held from src/gamez/zSystem/zsys_memory.cpp:125 */
/* port: duplicate of the gamez/zSystem/zsys_memory.cpp stub _strdup__FPCcPCci (this body is its candidate) */
#if 0
char* __strdup(const char* str, const char* file, int line)
{
	size_t len = strlen(str);
	len++;
	char* p = (char*)malloc(len);

	if (p == NULL)
	{
		zVid_Assert(false, INT_MAX, __FILE__, __LINE__);
		return NULL;
	}

	strcpy(p, str);
	zVid_Assert(len == 0 || p != NULL, INT_MAX, __FILE__, __LINE__);
	return p;
}
#endif

/* @socom-skeleton body __free__FPvPCci */
/* held from src/gamez/zSystem/zsys_memory.cpp:142 */
/* port: duplicate of the gamez/zSystem/zsys_memory.cpp stub _free__FPvPCci (this body is its candidate) */
#if 0
void _free(void* block, const char* file, int line)
{
	free(block);
}
#endif

/* @socom-skeleton body zsysSprGetPacket__FP8_word128 */
/* held from src/gamez/zSystem/zsys_spr.cpp:6 */
/* port: not in the ELF; the binary has zSysSprGetPacket__FPP1 (stub in zsys_spr.cpp) */
#if 0
_word128* zsysSprGetPacket(_word128* packet = NULL)
{
	sprBeingWritten = (_word128*)zSys.sprPacketBegin;

	if (sprBeingWritten == sprBeingKicked)
	{
		sprBeingWritten = (_word128*)(zSys.sprPx ^ 1);
		zSys.sprPx ^= 1;
	}

	if (packet)
		*packet = (_word128&)zSys.sprPacketEnd[zSys.sprPx - 16];

	zSys.sprPx ^= 1;
	return sprBeingWritten;
}
#endif

/* @socom-skeleton body zsys_AllocScratchpad__Fv */
/* held from src/gamez/zSystem/zsys_spr.cpp:23 */
/* port: not in the ELF; zSysInit (0x2f4df0) calls zsys_FullAllocAndFree instead */
#if 0
long128* zsys_AllocScratchpad()
{
	long128* spr = (long128*)zcalloc(1024, sizeof(long128));
	zSys.sprPacketBegin = spr;
	return spr;
}
#endif

/* @socom-skeleton body Print__4CTTYFPcUi */
/* held from src/gamez/zSystem/zsys_tty.cpp:12 */
/* port: not in the ELF; Print__4CTTYFPci is defined in gamez/zVideo/zvid_draw.cpp */
#if 0
void CTTY::Print(char* buffer, size_t size)
{
    memset(m_buffer, 0, 1024);
    strcpy_s(m_buffer, size, buffer);
}
#endif
