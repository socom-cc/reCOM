#ifndef STATE_H
#define STATE_H

/* port: forward declarations for names this header uses */
class CZSealBody;
struct _zrdr;

#include "gamez/zGame/zgame.h" /* CGameMenu: base of CLoadMenu */
#include "gamez/zUI/zui.h" /* CRenderableString (CLoadMenu) */
/* @socom-skeleton decl 9CE3Config */
class CE3Config
{
public:
	void Parse(_zrdr *);
};
/* @socom-skeleton end 9CE3Config */
/* @socom-skeleton decl 17CE3MissionPlayers */
class CE3MissionPlayers
{
public:
	void Parse(_zrdr *);
};
/* @socom-skeleton end 17CE3MissionPlayers */
/* @socom-skeleton decl 10CEntityItr */
class CEntityItr
{
public:
	void Advance();
	CZSealBody * GetSeal() const;
};
/* @socom-skeleton end 10CEntityItr */
/* @socom-skeleton decl 9CLoadMenu */
class CLoadMenu : public CGameMenu
{
public:
	/* no DWARF; layout (3520 bytes) from CLoadState::Init (0x37f5a8, which constructs it
	 * inline), PrepControls (0x37fa30) and MyTick (0x37f940) */
	CPlainBmp m_bitmaps[5];      /* +0x890 loading, loading glow, launch, launch glow, waiting glow */
	CRenderableString m_text[3]; /* +0xbb0 the multiplayer lines (client count, WAITING, HOST SELECTING MISSION) */
	f32 m_pulseTime;             /* +0xdb4 glow pulse, wraps at 1 */
	virtual ~CLoadMenu();
	virtual void MyTick(float);
	virtual char * GetReaderFileName();
	virtual void PrepControls(zdb::CTextureRelocMgr *);
};
/* @socom-skeleton end 9CLoadMenu */
#endif
