/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): wraps CameraZoom::AttachSeal (CCoreState::Init calls it across units, so --wrap sees it). The player's real
 * start comes from the AI maps (CMission::LoadVehicle 0x1fd2f4: CAiMaps::GetLocation /
 * GetCellCenter), which the port does not read yet, so every character stands at the
 * world origin, a corner of the m8 grid, looking out of it. This hook moves the player
 * node to the grid centre at the ground altitude there (CWorld::GetAltitude) so the
 * game's own camera and RenderWorld can be checked on real m8 data.
 * boot-textures: also dumps the GS texture buffers once (counts, ranges, fit). */
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_assetlib.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zIntersect/zintersect.h"
#include "gamez/zGame/zgame.h"
#include "gamez/zTexture/ztex.h"
#include "gamez/zVisual/zvis.h"

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);

static void DumpTexBuffers()
{
    zdb::CTexManager &tm = zdb::CTexManager::m_texmanager;
    SOCOM_PORT_TRACE("TEXB: area %u..%u, %u buffers, params %d %d %d %d (x1000)", zdb::CTexture::m_baseAddress,
        zdb::CTexture::m_endAddress, (unsigned)tm.size(), (int)(zdb::CTexManager::TexBufParams[0] * 1000),
        (int)(zdb::CTexManager::TexBufParams[1] * 1000), (int)(zdb::CTexManager::TexBufParams[2] * 1000),
        (int)(zdb::CTexManager::TexBufParams[3] * 1000));

    for (unsigned b = 0; b < tm.size(); b++)
    {
        zdb::CGSTexBuffer *buf = reinterpret_cast<zdb::CGSTexBuffer *>(tm[b]);
        unsigned texWords = 0, palWords = 0, fit = 0, nobuf = 0, mip = 0;
        unsigned next = buf->m_startAddress;

        for (auto p = buf->m_dyntex_list.m_pal_list.begin(); p != buf->m_dyntex_list.m_pal_list.end(); ++p)
        {
            palWords += (*p)->m_size / 256;
            next += (*p)->m_size / 256;
        }

        for (auto h = buf->m_dyntex_list.m_tex_list.begin(); h != buf->m_dyntex_list.m_tex_list.end(); ++h)
        {
            zdb::CTexture *t = (*h)->m_texture;
            texWords += t->m_gsWords;
            if (next + t->m_gsWords < buf->m_endAddress) { fit++; next += t->m_gsWords; }
            if (t->m_buffer == NULL) nobuf++;
            if (t->m_MIP1 != NULL) mip++;
        }

        SOCOM_PORT_TRACE("TEXB: [%u] %s %u..%u: %u textures (%u blocks, %u fit, %u without pixels, %u with MIPTBP1), %u palettes (%u blocks), chain %p ovf %d",
            b, buf->m_name ? buf->m_name : "(ui)", buf->m_startAddress, buf->m_endAddress,
            (unsigned)buf->m_dyntex_list.m_tex_list.size(), texWords, fit, nobuf, mip,
            (unsigned)buf->m_dyntex_list.m_pal_list.size(), palWords, buf->m_chainp, buf->m_checkForOverflow);
    }

    /* the first world textures: name, size, format, TEX0 */
    zdb::CGSTexBuffer *world = reinterpret_cast<zdb::CGSTexBuffer *>(tm[zdb::CTexManager::TexPhase[0][0]]);
    unsigned n = 0;
    for (auto h = world->m_dyntex_list.m_tex_list.begin(); h != world->m_dyntex_list.m_tex_list.end() && n < 12; ++h, ++n)
    {
        zdb::CTexture *t = (*h)->m_texture;
        unsigned long long tex0 = t->m_TEX0 ? *t->m_TEX0 : 0;
        SOCOM_PORT_TRACE("TEXW: %s %ux%u bits %u gs %u words %u pal %p TEX0 %08x%08x", (*h)->m_name ? (*h)->m_name : "?",
            t->m_width, t->m_height, t->m_texelBitSize, t->m_gsaddr, t->m_gsWords, t->m_palette,
            (unsigned)(tex0 >> 32), (unsigned)tex0);
    }

    for (auto l = zdb::CAssetMgr::m_assets.begin(); l != zdb::CAssetMgr::m_assets.end(); ++l)
        SOCOM_PORT_TRACE("TEXL: lib %s autoload %d phase %d: %u textures %u palettes", (*l)->m_name, (*l)->m_autoload,
            (int)(unsigned char)(*l)->m_renderphase, (unsigned)(*l)->m_textures.size(), (unsigned)(*l)->m_palettes.size());
}

static void DumpCharSets()
{
    zdb::CWorld *world = zdb::CWorld::m_world;
    if (world == NULL) return;
    SOCOM_PORT_TRACE("CHAR: %u sets, %u common-all handles, %u decal handles", (unsigned)world->m_TextureAssetCharacters.size(),
        (unsigned)world->m_TextureCharacterCommon.size(), (unsigned)world->m_TextureDecals.size());
    for (auto i = world->m_TextureAssetCharacters.begin(); i != world->m_TextureAssetCharacters.end(); ++i)
    {
        zdb::CTextureAssetCharacters *set = (zdb::CTextureAssetCharacters *)*i;
        zdb::CGSTexBuffer *b = set->m_texBuffer;
        SOCOM_PORT_TRACE("CHAR: set lib %s phase %d nodes %u (first %s) buffer %s: %u textures %u palettes",
            set->m_assetLib ? set->m_assetLib->m_name : "(null)", set->m_assetLib ? (int)(unsigned char)set->m_assetLib->m_renderphase : -1,
            (unsigned)set->m_nodes.size(), set->m_nodes.size() ? set->m_nodes[0]->m_name : "-", b && b->m_name ? b->m_name : "-",
            b ? (unsigned)b->m_dyntex_list.m_tex_list.size() : 0, b ? (unsigned)b->m_dyntex_list.m_pal_list.size() : 0);
    }
    CZSealBody *player = ftsGetPlayer();
    if (player != NULL)
    {
        zdb::CNode *n = player->m_node;
        SOCOM_PORT_TRACE("CHAR: player node %s active %d character %d visuals %u children %u hasMesh %d hasVisuals %d mesh %p pos %d %d %d",
            n->m_name, n->m_active, n->m_character, (unsigned)n->m_visual.size(), (unsigned)n->m_child.size(), n->m_hasMesh,
            n->m_hasVisuals, n->GetMesh(), (int)n->m_matrix.m_matrix[3][0], (int)n->m_matrix.m_matrix[3][1], (int)n->m_matrix.m_matrix[3][2]);
    }
}

extern unsigned numCharactersRendered;
extern "C" unsigned __real__ZN5CPipe11RenderWorldEPN3zdb6CWorldE(CPipe *pipe, zdb::CWorld *world);
extern "C" unsigned __wrap__ZN5CPipe11RenderWorldEPN3zdb6CWorldE(CPipe *pipe, zdb::CWorld *world)
{
    static unsigned frame = 0;
    unsigned r = __real__ZN5CPipe11RenderWorldEPN3zdb6CWorldE(pipe, world);
    frame++;
    if (frame <= 3 || frame % 300 == 0)
    {
        unsigned infov = 0;
        for (auto i = world->m_TextureAssetCharacters.begin(); i != world->m_TextureAssetCharacters.end(); ++i)
            infov += ((zdb::CTextureAssetCharacters *)*i)->m_numInFOV;
        SOCOM_PORT_TRACE("CHARF: frame %u characters rendered %u, in view %u", frame, numCharactersRendered, infov);
        if (frame % 600 == 0)
        {
            zdb::_globalLight &g = world->m_gLight;
            SOCOM_PORT_TRACE("LIGHT: dir0 %d %d %d col0 %d %d %d col1 %d %d %d ambient %d %d %d (x1000)",
                (int)(g.dir[0].x * 1000), (int)(g.dir[0].y * 1000), (int)(g.dir[0].z * 1000),
                (int)(g.col[0].x * 1000), (int)(g.col[0].y * 1000), (int)(g.col[0].z * 1000),
                (int)(g.col[1].x * 1000), (int)(g.col[1].y * 1000), (int)(g.col[1].z * 1000),
                (int)(g.ambient.x * 1000), (int)(g.ambient.y * 1000), (int)(g.ambient.z * 1000));
        }
    }
    return r;
}

/* TEST HOOK: skip the enemy characters ("m8_*") LoadVehicle asks for, to stay under the heap
   limit (the port runs out of memory at the ~18th of 41 vehicles: the menu state is never
   released). Only calls returning into CMission::LoadVehicle are filtered. */
extern "C" char _ZN8CMission11LoadVehicleEP16CVehicleRdrEntryb[];
extern "C" CCharacterType *__real__ZN14CCharacterType12GetByNameModEPKc(const char *name);
extern "C" CCharacterType *__wrap__ZN14CCharacterType12GetByNameModEPKc(const char *name)
{
    unsigned ra = (unsigned)__builtin_return_address(0);
    unsigned lv = (unsigned)_ZN8CMission11LoadVehicleEP16CVehicleRdrEntryb;
    if (name != NULL && ra >= lv - 0x600 && ra < lv + 0x800 /* also the .constprop clone just before */ && strncmp(name, "m8_", 3) == 0)
        return NULL;
    return __real__ZN14CCharacterType12GetByNameModEPKc(name);
}

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;

    DumpTexBuffers();
    DumpCharSets();

    /* boot-textures: the real spawn works now (AI maps); the move only gives the same view of
       the town as the first 3D screenshot */
    if (player != NULL && world != NULL)
    {
        float x = SOCOM_HOOK_X;
        float z = SOCOM_HOOK_Z;
        CPnt3D probe(x, 0.0f, z);
        zdb::IntersectStruct *ground = world->GetAltitude(&probe, 100000.0f);
        float y = ground != NULL ? ground->m_pos.y : 0.0f;
        player->m_node->SetPosition(x, y, z);
        SOCOM_PORT_TRACE("HOOK: player moved to %d %d %d (ground %p)", (int)x, (int)y, (int)z, ground);
    }

}
