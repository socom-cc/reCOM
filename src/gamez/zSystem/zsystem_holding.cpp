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

/* port: no stage-4 owner - the frame timing statics 0x4764c8-0x4764f0 (CCoreState::Tick
   writes them, CBench::Reset clears dmaTime); held here with the other CBench statics */
f32 CBench::preTask;
f32 CBench::postTask;
f32 CBench::inputTime;
f32 CBench::postCamUpdate;
f32 CBench::postAppCamTick;
f32 CBench::postCompassTick;
f32 CBench::postHUDTick;
f32 CBench::swapTime;
f32 CBench::drawTime;
f32 CBench::twoDTime;
f32 CBench::dmaTime;

/* port: no stage-4 owner - the particle counters 0x47650c-0x476518 (.sbss). CHUD::StatusLine's
   render report prints them (0x3db42c-0x3db444); nothing in the ELF writes them (no other $gp
   access, no address taken, CBench::Reset leaves them), so they stay 0 as in the original */
u32 CBench::countParticleSources;
u32 CBench::countParticleSourcesProcessed;
u32 CBench::countParticlesProcessed;
u32 CBench::countParticlesDrawn;

/* @socom-skeleton body zSys */
/* held from src/gamez/zSystem/zsys_main.cpp:3 */
_zsys_public zSys;

/* @socom-skeleton body _HeapSize */
/* held from src/gamez/zSystem/zsys_memory.cpp:11 */
size_t __HeapSize = 0; /* port: __HeapSize (C name; zsys_FullAllocAndFree stores it at 0x2f4964) */
