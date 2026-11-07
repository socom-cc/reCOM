#ifndef ZSYS_BENCH_H
#define ZSYS_BENCH_H
#include "zsys.h"

class CBench
{
public:
	static void Reset(); /* 0x2f3730 uses no object: CCoreState::Tick calls it with a stale a0 */

	/* frame timing stamps, RCNT0 * zSys.timerScale (CCoreState::Tick 0x17ccd0) */
	static f32 preTask;
	static f32 postTask;
	static f32 inputTime;
	static f32 postCamUpdate;
	static f32 postAppCamTick;
	static f32 postCompassTick;
	static f32 postHUDTick;
	static f32 swapTime;
	static f32 drawTime;
	static f32 twoDTime;
	static f32 dmaTime;

	static u32 countNodes;
	static u32 countRenderNodes;
	static u32 countAlphaNodes;
	static u32 countClutterNodes;
	static u32 countVisuals;
	static u32 countAlphaVisuals;
	static f32 drawTimeX[10]; /* DWARF array_type float[0..9] (hud_devtext.cpp); CPipe::RenderWorld fills [0..8] */
};
#endif