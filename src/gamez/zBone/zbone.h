#ifndef ZBONE_H
#define ZBONE_H

/* port: forward declarations for names this header uses */
class CZSIScript;
#include "gamez/zArchive/zar.h"

bool zBoneInit();
bool zBoneOpen();
bool zBoneLoadAll();
bool zBoneClose();

class CScriptArchive : public zar::CZAR
{
public:
    
	/* @socom-skeleton decl 14CScriptArchive */
public:
	~CScriptArchive();
	void Fetch(const char *, CZSIScript *, bool);
	void LoadAll();
	/* @socom-skeleton end 14CScriptArchive */
};

/* port: bone_archive_version is file-local (static) data in bone_init.cpp (ELF local symbol) */
extern CScriptArchive boneArchive;
extern size_t Sizeof_MotionRdr;
extern void* pBuffer_MotionRdr;
#endif