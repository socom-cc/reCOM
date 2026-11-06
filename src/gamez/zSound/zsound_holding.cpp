/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include "gamez/zSound/zsnd.h"

/* @socom-skeleton body g_iReverbTime */
/* held from src/gamez/zSound/zsnd_csnd.cpp:11 */
/* port: duplicate of gamez/zSound/zsnd_csnd.cpp (g_iReverbTime__23@unnamed@zsnd_csnd_cpp@) */
#if 0
s32 g_iReverbTime = 0;
#endif

/* @socom-skeleton body m_snd_data__4CSnd */
/* held from src/gamez/zSound/zsnd_csnd.cpp:24 */
u8* CSnd::m_snd_data = NULL; /* port: unproven - not in the ELF; provisional storage existing bodies use */

/* @socom-skeleton body m_snd_len__4CSnd */
/* held from src/gamez/zSound/zsnd_csnd.cpp:25 */
u32 CSnd::m_snd_len = 0; /* port: unproven - not in the ELF; provisional storage existing bodies use */

/* @socom-skeleton body m_soundmap__4CSnd */
/* held from src/gamez/zSound/zsnd_csnd.cpp:34 */
std::unordered_map<const char*, CSnd*> CSnd::m_soundmap; /* port: unproven - not in the ELF; provisional storage existing bodies use */

/* @socom-skeleton body sound_rdr */
/* held from src/gamez/zSound/zsnd_csnd.cpp:38 */
/* port: not in the ELF; the binary's object is the LOCAL _sound_rdr in zsnd_csnd.cpp */
#if 0
_zrdr* sound_rdr = NULL;
#endif
