#ifndef STATE_H
#define STATE_H

/* port: forward declarations for names this header uses */
class CZSealBody;
struct _zrdr;

#include "gamez/zGame/zgame.h" /* CGameMenu: base of CLoadMenu */
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
	virtual ~CLoadMenu();
	virtual void MyTick(float);
	virtual char * GetReaderFileName();
	virtual void PrepControls(zdb::CTextureRelocMgr *);
};
/* @socom-skeleton end 9CLoadMenu */
#endif
