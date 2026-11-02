#ifndef NODE_SAVELOAD_H
#define NODE_SAVELOAD_H
#include "znode.h"
#include "node_world.h"

#include "gamez/zArchive/zar.h"
#include "gamez/zSystem/zsys.h"

#define TYPE_TEXTURES 1
#define TYPE_MODELS   2
#define TYPE_PALETTES 4
#define TYPE_ALL      255

namespace zdb
{
    class CSaveLoad
    {
        friend class CNode;
    public:
        CSaveLoad();

        CWorld* Load(const char* path);
        bool LoadAssetLib(CWorld* world, CAssetLib* library, u32 type);
        bool LoadAssetLib_PS2(CWorld* world, CAssetLib* library, u32 type);
        bool LoadPalettes_PS2(CAssetLib* library);
        bool LoadTextures_PS2(CAssetLib* library);
    public:
        CWorld* m_world;
        zar::CZAR m_zfile;
        char m_zed_filename[1024];
        s32 m_version;
        /* @socom-skeleton decl Q23zdb9CSaveLoad */
public:
        ~CSaveLoad();
        bool LoadAssetLib_PS2(zdb::CWorld *, zdb::CAssetLib *, int);
        unsigned char LoadAssetLib(zdb::CWorld *, zdb::CAssetLib *, int);
        /* @socom-skeleton end Q23zdb9CSaveLoad */
    };
}
#endif