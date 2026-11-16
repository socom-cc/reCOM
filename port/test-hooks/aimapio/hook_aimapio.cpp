/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): the AI map loader (src/gamez/zAI/ai_mapio.cpp, CAiMap::Read 0x189390).
 *  - wraps CAiMap::Read: after every real read one line with the map's version, sizes, table
 *    counts and FNV-1a sums of its cells and tables ("HOOK: aimapio map ..."), so two builds can be
 *    compared on the disc's maps (all version 19). Builds against any tree.
 *  - -DAIMAPIO_SELFTEST (needs the old record types in zai.h): after the first real map, the old
 *    formats the disc does not have. For every version 0-20 the hook writes small synthetic files
 *    from the layouts declared in zai.h (cell_v2 / cell_v3 / action_v15 / action_v18 / region_v4,
 *    every bit a converter must not take set to 1) and serves them through CBufferIO:
 *      cells:  CAiMap::read_cells on a 2 x 2 map, each converted cell compared bit for bit with
 *              the cell the layout says (raw versions: the bytes as written);
 *      read:   the whole CAiMap::Read: result, version, parameters (52-byte head and the fields
 *              each version adds, or all 164 bytes), names, converted actions and regions, links,
 *              spores, lines (line_data from 10), scanlines (built before 15, read from 15), map
 *              extra bytes (13 on), and that the reader stopped exactly at the end of the file.
 *    One "HOOK: aimapio v<n> cells|read PASS|FAIL" line per test, each mismatch named, and a total.
 * Build: port/test-hooks/aimapio/build.sh <build> [pad] [-- -DAIMAPIO_SELFTEST]. */
#include "gamez/zAI/zai.h"
#include "gamez/zUtil/util_systemio.h"
#include "gamez/zSystem/zsys.h"
#include <string.h>

extern "C" bool __real__ZN6CAiMap4ReadER7CFileIO(CAiMap *self, CFileIO &io);

namespace
{
u32 fnv(u32 h, const void *p, u32 n)
{
    const unsigned char *b = static_cast<const unsigned char *>(p);

    for (u32 i = 0; i < n; i++)
        h = (h ^ b[i]) * 16777619u;

    return h;
}

template <class V> u32 fnv_table(u32 h, const V &v)
{
    return v.size() != 0 ? fnv(h, &v[0], v.size() * sizeof(v[0])) : h;
}

void summary(const CAiMap *m, bool ok)
{
    u32 cells = m->m_cell != NULL ? fnv(2166136261u, m->m_cell, m->m_cellcount * sizeof(CAiCell)) : 0;
    u32 t = 2166136261u;
    t = fnv_table(t, m->m_namesTable);
    t = fnv_table(t, m->m_actionTable);
    t = fnv_table(t, m->m_linksTable);
    t = fnv_table(t, m->m_regionTable);
    t = fnv_table(t, m->m_sporeTable);

    for (CAiMap::lines::const_iterator i = m->m_lineTable.begin(); i != m->m_lineTable.end(); ++i)
    {
        t = fnv_table(t, static_cast<const CAiMapLocVec &>(*i));
        t = fnv(t, static_cast<const line_data *>(&*i), 4);
    }

    for (CAiMap::scanlines::const_iterator i = m->m_scanlines.begin(); i != m->m_scanlines.end(); ++i)
    {
        t = fnv(t, &i->m_start, 2);
        t = fnv(t, &i->m_end, 2);
        u32 first = i->m_cell - m->m_cell; /* the row's first cell (pointers differ per heap) */
        t = fnv(t, &first, 4);
    }

    u32 ex = m->m_mapex != NULL ? fnv(2166136261u, m->m_mapex, m->m_mapex_bytes * m->m_cellcount) : 0;
    SOCOM_PORT_TRACE("HOOK: aimapio map v%u ok %d '%s' nx %u ny %u cells %u compressed %u names %u actions %u "
                     "links %u regions %u spores %u lines %u readers %u routes %u scanlines %u mapex %u "
                     "cellsum %08x tablesum %08x exsum %08x", m->m_version, ok ? 1 : 0, m->m_name, m->m_nx,
                     m->m_ny, m->m_cellcount, m->m_compressed, (u32)m->m_namesTable.size(),
                     (u32)m->m_actionTable.size(), (u32)m->m_linksTable.size(), (u32)m->m_regionTable.size(),
                     (u32)m->m_sporeTable.size(), (u32)m->m_lineTable.size(), (u32)m->m_readerTable.size(),
                     (u32)m->m_routeTable.size(), (u32)m->m_scanlines.size(), m->m_mapex_bytes, cells, t, ex);
}

bool g_selftest_done;
} // namespace

#ifdef AIMAPIO_SELFTEST
namespace
{
unsigned char g_buf[2048];
u32 g_len;
u32 g_ver;
int g_fail;
int g_total_fail;
int g_tests;

void put(const void *p, u32 n)
{
    memcpy(g_buf + g_len, p, n);
    g_len += n;
}

void put32(u32 v) { put(&v, 4); }
void putf(f32 v) { put(&v, 4); }

void check(bool ok, const char *what, u32 got, u32 want)
{
    if (!ok)
    {
        g_fail++;
        SOCOM_PORT_TRACE("HOOK: aimapio v%u   mismatch %s: got 0x%x want 0x%x", g_ver, what, got, want);
    }
}

#define CHK(what, got, want) check((u32)(got) == (u32)(want), what, (u32)(got), (u32)(want))

u32 word(const void *p)
{
    u32 w;
    memcpy(&w, p, 4);
    return w;
}

CAiMapLoc loc(u32 x, u32 y)
{
    return CAiMapLoc(x, y, 0);
}

/* serves g_buf through a CBufferIO (the stream frees its _malloc'd copy on Close) */
void open(CBufferIO &io)
{
    void *copy = _malloc(g_len, "hook_aimapio.cpp", 1);
    memcpy(copy, g_buf, g_len);
    io.Open(copy, g_len);
}

void begin(u32 v)
{
    g_ver = v;
    g_fail = 0;
    g_len = 0;
}

void end(const char *test)
{
    g_tests++;
    g_total_fail += g_fail != 0;
    SOCOM_PORT_TRACE("HOOK: aimapio v%u %s %s (%u bytes, %d mismatches)", g_ver, test, g_fail == 0 ? "PASS" : "FAIL",
                     g_len, g_fail);
}

/* the cell test values: every field distinct per cell */
struct CellVals
{
    u32 soil, name, action, link, alt, bnd, mes, dir;
    s16 f, g;
};

CellVals cellvals(int i, bool flags)
{
    CellVals c;
    c.soil = 5 + i;
    c.name = flags ? (i & 1) : 0;
    c.action = flags ? ((i >> 1) & 1) : 0;
    c.link = flags ? (i == 2) : 0;
    c.alt = 100 * i + 7;
    c.bnd = i & 3;
    c.mes = (i & 1) ^ 1;
    c.dir = 9 - i;
    c.f = (s16)(-100 - i);
    c.g = (s16)(200 + i);
    return c;
}

/* writes cell i in version v's layout; returns the cell read_cells must make of it */
CAiCell put_cell(u32 v, int i, bool flags)
{
    CellVals c = cellvals(i, flags);
    CAiCell want;
    memset(&want, 0, sizeof(want));

    if (v == 2)
    {
        cell_v2 o;
        memset(&o, 0xff, sizeof(o));
        o.m_soil = c.soil;
        o.m_name = c.name;
        o.m_action = c.action;
        o.m_link = c.link;
        o.m_astar_dir = c.dir;
        o.m_astar_f = c.f;
        o.m_astar_g = c.g;
        put(&o, sizeof(o));
    }
    else if (v >= 3 && v <= 7)
    {
        cell_v3 o;
        memset(&o, 0xff, sizeof(o));
        o.m_soil = c.soil;
        o.m_name = c.name;
        o.m_action = c.action;
        o.m_link = c.link;
        o.m_altitude = c.alt;
        o.m_boundary = c.bnd;
        o.m_mes = c.mes;
        o.m_astar_dir = c.dir;
        o.m_astar_f = c.f;
        o.m_astar_g = c.g;
        put(&o, sizeof(o));
        want.m_altitude = c.alt;
        want.m_boundary = c.bnd;
        want.m_mes = c.mes;
    }
    else
    {
        /* the current cell, read whole: every field, the shadow / inside / ... bits too */
        unsigned char raw[8];

        for (int k = 0; k < 8; k++)
            raw[k] = (unsigned char)(0x11 * (i + 1) + 3 * k);

        if (!flags)
            raw[0] &= 0x1f, raw[1] &= 0xfe; /* name / action / occupied and link off */

        put(raw, 8);
        memcpy(&want, raw, 8);
        return want;
    }

    want.m_soil = c.soil;
    want.m_name = c.name;
    want.m_action = c.action;
    want.m_link = c.link;
    want.m_astar_dir = c.dir;
    want.m_astar_f = c.f;
    want.m_astar_g = c.g;
    return want;
}

void test_cells(u32 v)
{
    begin(v);
    CAiCell want[4];

    for (int i = 0; i < 4; i++)
        want[i] = put_cell(v, i, true);

    CAiMap *map = new CAiMap();
    map->m_version = v;
    map->m_nx = 2;
    map->m_ny = 2;
    map->m_cellcount = 4;
    CBufferIO io;
    open(io);
    map->read_cells(io);
    CHK("bytes read", io.ftell(), g_len);
    CHK("cellcount", map->m_cellcount, 4);

    for (int i = 0; i < 4; i++)
    {
        char what[32];
        strcpy(what, "cell 0 word 0");
        what[5] = (char)('0' + i);
        CHK(what, word(&map->m_cell[i]), word(&want[i]));
        what[12] = '1';
        CHK(what, word(reinterpret_cast<char *>(&map->m_cell[i]) + 4), word(reinterpret_cast<char *>(&want[i]) + 4));
    }

    io.Close();
    delete map;
    end("cells");
}

/* the synthetic map's records */
const char REGION_NAME[16] = { 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P' };

void test_read(u32 v)
{
    begin(v);
    put32(v);
    bool known = v >= 2 && v <= 19;

    AIMAP_PARAMS p;
    memset(&p, 0, sizeof(p));
    p.m_bbox.m_min = CPnt3D(-1.0f, -2.0f, -3.0f);
    p.m_bbox.m_max = CPnt3D(4.0f, 5.0f, 6.0f);
    p.m_nx = 2;
    p.m_ny = 2;
    p.m_dx = 2.5f;
    p.m_dy = 4.5f;
    p.m_idx = 0.4f;
    p.m_idy = 0.25f;
    p.m_floor = 3;
    strcpy(p.m_name, "oldmap");
    p.m_resolution = 0.75f;
    p.m_flags = 0x10;
    p.m_slope_threshold = 0.5f;
    p.m_mapex_bytes = 2;
    p.m_cellcount = 4;
    p.m_revision = 7;

    if (v >= 2 && v <= 12)
    {
        put(&p, 52);

        if (v >= 5)
            put(p.m_name, 32);
        if (v >= 7)
            putf(p.m_resolution);
        if (v >= 10)
            put32(p.m_flags);
        if (v >= 11)
            putf(p.m_slope_threshold);
    }
    else if (known)
    {
        put(&p, sizeof(p));
    }

    if (known)
    {
        for (int i = 0; i < 4; i++)
            put_cell(v, i, false);
    }

    if (known && v >= 15)
    {
        for (int y = 0; y < 2; y++)
        {
            CAiMap::scanline row;
            memset(&row, 0, sizeof(row));
            row.m_start = 0;
            row.m_end = 2;
            put(&row, sizeof(row));
        }
    }

    CAiMap::name nm;
    memset(&nm, 0, sizeof(nm));
    nm.m_loc = loc(0, 1);
    nm.m_altitude = 12.5f;
    strcpy(nm.m_name, "nm1");
    nm.m_type = 3;

    CAiMapLoc ex[6] = { loc(0, 1), loc(1, 0), loc(1, 1), loc(0, 0), loc(1, 1), loc(0, 1) };
    CAiMap::link ln;
    ln.m_loc = loc(1, 0);
    ln.m_link = loc(0, 0);
    CAiMap::spore sp;
    memset(&sp, 0, sizeof(sp));
    sp.m_loc = loc(1, 1);
    sp.m_dir = 2;
    sp.m_id = 77;
    sp.m_altitude = 3.5f;
    CAiMap::action cur;
    memset(&cur, 0, sizeof(cur));
    CAiMap::region rcur;
    memset(&rcur, 0, sizeof(rcur));

    if (known && v >= 4)
    {
        put32(1);
        put(&nm, sizeof(nm));

        put32(1);

        if (v <= 15)
        {
            action_v15 a;
            memset(&a, 0xff, sizeof(a));
            a.m_loc = loc(1, 1);
            a.m_direction = 5;
            a.m_actionId = 1234;
            a.m_type = 17;
            a.m_locExValid = 1;
            memcpy(a.m_locEx, ex, sizeof(a.m_locEx));
            put(&a, sizeof(a));
        }
        else if (v <= 18)
        {
            action_v18 a;
            memset(&a, 0xff, sizeof(a));
            a.m_loc = loc(1, 1);
            a.m_direction = 5;
            a.m_type = 17;
            a.m_locExValid = 1;
            a.m_offset = 3;
            a.m_type_invalid = 1;
            memcpy(a.m_locEx, ex, sizeof(a.m_locEx));
            put(&a, sizeof(a));
        }
        else
        {
            cur.m_loc = loc(1, 1);
            cur.m_direction = 5;
            cur.m_actionId = 1234;
            cur.m_state = 0;
            cur.m_type = 17;
            cur.m_locExValid = 1;
            cur.m_offset = 3;
            memcpy(cur.m_locEx, ex, sizeof(cur.m_locEx));
            cur.m_region = loc(0, 1);
            put(&cur, sizeof(cur));
        }

        if (v >= 12)
        {
            put32(1);
            put(&ln, sizeof(ln));
        }
        else
        {
            put32(0); /* no links before 12: the drop runs before the scanlines exist (see the note) */
        }

        put32(1);

        if (v <= 8)
        {
            region_v4 r;
            memset(&r, 0xff, sizeof(r));
            r.m_loc = loc(0, 0);
            r.m_dx = 2;
            r.m_dy = 2;
            memcpy(r.m_name, REGION_NAME, 16);
            put(&r, sizeof(r));
        }
        else
        {
            rcur.m_loc = loc(0, 0);
            rcur.m_dx = 2;
            rcur.m_dy = 2;
            rcur.m_type = 6;
            rcur.m_flags = 0x123;
            strcpy(rcur.m_name, "region9");
            put(&rcur, sizeof(rcur));
        }

        put32(1);
        put(&sp, sizeof(sp));
    }

    line_data ld;
    memset(&ld, 0, sizeof(ld));
    ld.m_type = 4;
    ld.m_id = 9;
    ld.m_polygon = 1;

    if (known && v >= 6)
    {
        put32(1);
        put32(2);
        CAiMapLoc pts[2] = { loc(0, 0), loc(1, 1) };
        put(pts, sizeof(pts));

        if (v >= 10)
            put(&ld, 4);
    }

    if (known && v >= 14)
        put32(0); /* readers */

    if (known && v >= 18)
        put32(0); /* routes */

    unsigned char mapex[8] = { 0xe0, 0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7 };

    if (known && v >= 13)
        put(mapex, sizeof(mapex));

    CAiMap *map = new CAiMap();
    CBufferIO io;
    open(io);
    bool ok = __real__ZN6CAiMap4ReadER7CFileIO(map, io);

    CHK("result", ok, known);
    CHK("version", map->m_version, v);
    CHK("bytes read", io.ftell(), g_len);

    if (known)
    {
        CHK("nx", map->m_nx, 2);
        CHK("ny", map->m_ny, 2);
        CHK("floor", map->m_floor, 3);
        CHK("bbox max z", word(&map->m_bbox.m_max.z), word(&p.m_bbox.m_max.z));
        CHK("idy", word(&map->m_idy), word(&p.m_idy));
        CHK("name", strcmp(map->m_name, v >= 5 ? "oldmap" : ""), 0);
        f32 res = v >= 7 ? 0.75f : 0.5f, slope = v >= 11 ? 0.5f : 0.7853982f;
        CHK("resolution", word(&map->m_resolution), word(&res));
        CHK("slope", word(&map->m_slope_threshold), word(&slope));
        CHK("flags", map->m_flags, v >= 10 ? 0x10 : 0); /* CreateGraph clears bit 0 (no routes) */
        CHK("mapex bytes", map->m_mapex_bytes, v >= 13 ? 2 : 0);
        if (v >= 13) /* the constructor leaves m_revision unset */
            CHK("revision", map->m_revision, 7);
        CHK("cellcount", map->m_cellcount, 4);
        CHK("cell 3 soil", map->m_cell != NULL ? map->m_cell[3].m_soil : 99, (v <= 7) ? 8 : (0x44 & 0x1f));
        CHK("scanlines", map->m_scanlines.size(), 2);

        for (u32 y = 0; y < map->m_scanlines.size(); y++)
        {
            CHK("row start", map->m_scanlines[y].m_start, 0);
            CHK("row end", map->m_scanlines[y].m_end, 2);
            CHK("row cell", map->m_scanlines[y].m_cell - map->m_cell, 2 * y);
        }

        CHK("mapex", map->m_mapex != NULL ? word(map->m_mapex + 4) : 0, v >= 13 ? word(mapex + 4) : 0);
    }

    u32 tables = known && v >= 4;
    CHK("names", map->m_namesTable.size(), tables);
    CHK("actions", map->m_actionTable.size(), tables);
    CHK("links", map->m_linksTable.size(), tables && v >= 12);
    CHK("regions", map->m_regionTable.size(), tables);
    CHK("spores", map->m_sporeTable.size(), tables);
    CHK("lines", map->m_lineTable.size(), known && v >= 6);

    if (tables && map->m_namesTable.size() == 1)
    {
        const CAiMap::name &n = map->m_namesTable[0];
        CHK("name loc", word(&n.m_loc), word(&nm.m_loc));
        CHK("name text", strcmp(n.m_name, "nm1"), 0);
        CHK("name type", n.m_type, 3);
    }

    if (tables && map->m_actionTable.size() == 1)
    {
        const CAiMap::action &a = map->m_actionTable[0];
        CHK("action loc", word(&a.m_loc), word(&ex[2]));
        CHK("action direction", a.m_direction, 5);
        CHK("action id", a.m_actionId, v >= 16 && v <= 18 ? 0xffff : 1234); /* v16-18: id not copied (ELF) */
        CHK("action state", a.m_state, 0);
        CHK("action type", a.m_type, 17);
        CHK("action locExValid", a.m_locExValid, 1);
        CHK("action offset", a.m_offset, v <= 16 ? 8 : 3); /* < 17: set to 8 after the read */
        CHK("action type_invalid", a.m_type_invalid, v >= 16 && v <= 18 ? 1 : 0);

        for (int k = 0; k < 6; k++)
        {
            u32 want = (v <= 15 && k >= 3) ? word(CAiMapLoc::invalid) : word(&ex[k]);
            CHK("action locEx", word(&a.m_locEx[k]), want);
        }

        if (v >= 16)
            CHK("action region", word(&a.m_region), v == 19 ? word(&cur.m_region) : word(CAiMapLoc::invalid));
    }

    if (tables && map->m_regionTable.size() == 1)
    {
        const CAiMap::region &r = map->m_regionTable[0];
        CHK("region loc", word(&r.m_loc), 0);
        CHK("region dx", r.m_dx, 2);
        CHK("region dy", r.m_dy, 2);
        CHK("region type", r.m_type, v <= 8 ? 0 : 6);
        CHK("region nodisplay", r.m_nodisplay, v <= 8 ? 1 : 0);
        CHK("region flags", r.m_flags, v <= 8 ? 0 : 0x123);
        CHK("region name", strcmp(r.m_name, v <= 8 ? "ABCDEFGHIJKLMNO" : "region9"), 0);
    }

    if (tables && map->m_linksTable.size() == 1)
        CHK("link", word(&map->m_linksTable[0].m_link), word(&ln.m_link));

    if (tables && map->m_sporeTable.size() == 1)
        CHK("spore", memcmp(&map->m_sporeTable[0], &sp, sizeof(sp)), 0);

    if (known && v >= 6 && map->m_lineTable.size() == 1)
    {
        const CAiMap::line &l = map->m_lineTable[0];
        CHK("line points", l.size(), 2);
        CHK("line point 1", l.size() == 2 ? word(&l[1]) : 0, word(&ex[2]));
        line_data none;
        memset(&none, 0, sizeof(none));
        CHK("line data", word(static_cast<const line_data *>(&l)), v >= 10 ? word(&ld) : word(&none));
    }

    io.Close();
    delete map;
    end("read");
}

void selftest()
{
    SOCOM_PORT_TRACE("HOOK: aimapio selftest: sizes cell_v2 %u cell_v3 %u action_v15 %u action_v18 %u region_v4 %u "
                     "(want 12 8 24 36 24)", (u32)sizeof(cell_v2), (u32)sizeof(cell_v3), (u32)sizeof(action_v15),
                     (u32)sizeof(action_v18), (u32)sizeof(region_v4));

    for (u32 v = 0; v <= 20; v++)
    {
        if (v <= 18)
            test_cells(v);

        test_read(v);
    }

    SOCOM_PORT_TRACE("HOOK: aimapio selftest: %d tests, %d failed", g_tests, g_total_fail);
}
} // namespace
#endif

extern "C" bool __wrap__ZN6CAiMap4ReadER7CFileIO(CAiMap *self, CFileIO &io)
{
    bool ok = __real__ZN6CAiMap4ReadER7CFileIO(self, io);
    summary(self, ok);

    if (!g_selftest_done)
    {
        g_selftest_done = true;
#ifdef AIMAPIO_SELFTEST
        selftest();
#endif
    }

    return ok;
}
