#ifndef ZSYS_SPR_H
#define ZSYS_SPR_H
#include "zsys.h"

/// <summary>
/// Class for dealing with the ScratchPad, a very-fast and efficient zone of memory.
/// </summary>
class CSPR
{
public:
	/* both static: callers pass the packet in a0 (CVisual::VuUpdate 0x30a900) */
	static _word128* Copy(_word128* toSPR, _word128* fromMem, s32 qwc);
	static _word128* Kick(_word128* end, bool getNext);
	/* @socom-skeleton decl 4CSPR */
public:
	static _word128* m_sprPacketEnd; /* last usable qword of m_sprPacket (zSysSprGetPacket) */
	static _word128* m_sprPacket;    /* the scratchpad packet being written */
	/* @socom-skeleton end 4CSPR */
};
#endif