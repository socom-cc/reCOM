#ifndef ZSYS_SPR_H
#define ZSYS_SPR_H
#include "zsys.h"

/// <summary>
/// Class for dealing with the ScratchPad, a very-fast and efficient zone of memory.
/// </summary>
class CSPR
{
public:
	_word128* Copy(_word128* toSADR, _word128* toMADR, s32 toQWC);
	_word128* Kick(_word128* packet, bool unknown1);
	/* @socom-skeleton decl 4CSPR */
public:
	static int m_sprPacketEnd;
	static int m_sprPacket;
	/* @socom-skeleton end 4CSPR */
};
#endif