/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body g_iReverbTime */
/* held from src/gamez/zSound/zsnd_csnd.cpp:11 */
s32 g_iReverbTime = 0;

/* @socom-skeleton body m_snd_data__4CSnd */
/* held from src/gamez/zSound/zsnd_csnd.cpp:24 */
u8* CSnd::m_snd_data = NULL;

/* @socom-skeleton body m_snd_len__4CSnd */
/* held from src/gamez/zSound/zsnd_csnd.cpp:25 */
u32 CSnd::m_snd_len = 0;

/* @socom-skeleton body m_soundmap__4CSnd */
/* held from src/gamez/zSound/zsnd_csnd.cpp:34 */
std::unordered_map<const char*, CSnd*> CSnd::m_soundmap;

/* @socom-skeleton body sound_rdr */
/* held from src/gamez/zSound/zsnd_csnd.cpp:38 */
_zrdr* sound_rdr = NULL;
