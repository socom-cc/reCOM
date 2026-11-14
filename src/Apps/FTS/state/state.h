#ifndef STATE_H
#define STATE_H

/* port: forward declarations for names this header uses */
class CZSealBody;
struct _zrdr;

#include "gamez/zGame/zgame.h" /* CGameMenu: base of CLoadMenu */
#include "gamez/zUI/zui.h" /* CRenderableString (CLoadMenu) */
#include "gamez/zEntity/zentity.h" /* CEntityList (CEntityItr) */
#include "gamez/zNetwork/znet.h" /* MP_GAME_TYPE (CE3MissionPlayers) */
#include "gamez/zSystem/zsys.h" /* CSaferStr */
#include <map>
/* @socom-skeleton decl 17CE3MissionPlayers */
class CE3MissionPlayers
{
public:
	/* DWARF CE3MissionPlayers (140 bytes, st_load.cpp): one e3config.rdr mission entry. Seals
	 * fill slots 0-7, terrorists 8-15 (Parse 0x37dbf0). The copy ctor (0x37e420) and dtor
	 * (0x37e4e0) emitted in st_load.cpp are the implicit ones. */
	CSaferStr m_type[16];       /* +0x0 */
	CSaferStr m_name[16];       /* +0x40 */
	MP_GAME_TYPE m_game_type;   /* +0x80 */
	s32 m_game_time;            /* +0x84 seconds */
	s32 m_round_count;          /* +0x88 */
	CE3MissionPlayers() : m_game_type(MP_GAME_TYPE::MP_GAME_DEATHMATCH) {} /* port: inline in CE3Config::Parse (0x37e1fc: type 6) */
	void Parse(_zrdr *);
};
/* @socom-skeleton end 17CE3MissionPlayers */
/* @socom-skeleton decl 9CE3Config */
class CE3Config
{
public:
	/* DWARF CE3Config (16 bytes): the missions of e3config.rdr by name (CLoadState::Tick
	 * looks the database up in it for a network game's type, time and rounds) */
	std::map<CSaferStr, CE3MissionPlayers> m_mission_players; /* +0x0 */
	void Parse(_zrdr *);
};
/* @socom-skeleton end 9CE3Config */
/* @socom-skeleton decl 10CEntityItr */
class CEntityItr
{
public:
	/* DWARF CEntityItr (8 bytes, st_exit.cpp): an entity-list position and how many places
	 * it has moved. Built inline by its users (port: this ctor). */
	CEntityList::iterator _it; /* +0x0 */
	s32 _iIdx;                 /* +0x4 */
	CEntityItr(CEntityList::iterator it) : _it(it), _iIdx(0) {}
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
/* port: no DWARF type. CExitState::Init (0x3208ec) news 2192 bytes (sizeof CGameMenu, its
 * vptr at +0x884) and sets the CExitMenu vtable (0x472fa0): the dtor 0x320670,
 * CGameMenu's MyTick and PrepControls, its own GetReaderFileName 0x321310. */
class CExitMenu : public CGameMenu
{
public:
	virtual ~CExitMenu() {} /* 0x320670: only ~CGameMenu */
	virtual char * GetReaderFileName();
};
/* port: DWARF CMPExitMenu (2208 bytes, st_mpexit.cpp; no skeleton fence): the multiplayer
 * debrief menu (vtable 0x474850: dtor 0x3dcc00, CGameMenu's MyTick and PrepControls, its own
 * GetReaderFileName 0x3de100). CMPExitState::Init news it and sets m_gameover. */
class CMPExitMenu : public CGameMenu
{
public:
	bool m_gameover; /* +0x890 the last round: the final screen */
	CMPExitMenu() : m_gameover(false) {}
	virtual ~CMPExitMenu() {} /* 0x3dcc00: only ~CGameMenu */
	virtual char * GetReaderFileName();
};
#endif
