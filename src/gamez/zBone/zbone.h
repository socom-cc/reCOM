#ifndef ZBONE_H
#define ZBONE_H

/* port: forward declarations for names this header uses */
class CZSIScript;
#include <list>
#include "gamez/zArchive/zar.h"

bool zBoneInit();
bool zBoneOpen();
bool zBoneLoadAll();
bool zBoneClose();

class CScriptArchive : public zar::CZAR
{
public:
	/* the scripts fetched so far. port: layout guess - the ELF keeps this list at +0x0 and
	 * the archive at +0xc (CZAR::Fetch gets boneArchive + 0xc) */
	std::list<CZSIScript*> m_scripts;

	/* @socom-skeleton decl 14CScriptArchive */
public:
	~CScriptArchive();
	bool Fetch(const char *, CZSIScript *, bool); /* bool: 0x1dd220 */
	bool LoadAll(); /* bool: 0x1dd1f0 */
	/* @socom-skeleton end 14CScriptArchive */
};

/* port: bone_archive_version is file-local (static) data in bone_init.cpp (ELF local symbol) */
extern CScriptArchive boneArchive;
extern size_t Sizeof_MotionRdr;
extern void* pBuffer_MotionRdr;
#endif