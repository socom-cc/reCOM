#ifndef ZSYS_BENCH_H
#define ZSYS_BENCH_H
#include "zsys.h"

class CBench
{
public:
	void Reset();

	static u32 countNodes;
	static u32 countRenderNodes;
	static u32 countAlphaNodes;
	static u32 countClutterNodes;
	static u32 countVisuals;
	static u32 countAlphaVisuals;
	static f32 drawTimeX[10]; /* DWARF array_type float[0..9] (hud_devtext.cpp); CPipe::RenderWorld fills [0..8] */
};
#endif