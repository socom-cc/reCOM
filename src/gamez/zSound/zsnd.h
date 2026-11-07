#ifndef ZSOUND_H
#define ZSOUND_H

#include <list>
#include <map>
#include <string>
#include <vector>
#include <unordered_map>

#include "gamez/zArchive/zar.h"
#include "gamez/zMath/zmath.h"
#include "gamez/zReader/zrdr.h"
#include "gamez/zSystem/zsys.h"
#include "gamez/zValve/zvalve.h"

class CSnd;
class CSndInstance;
class CSndSequence;

namespace zdb
{
	class CNode;
}

/* DWARF: 1-byte enumerations (CSnd +0x1f, +0x20) */
enum SOUND_TYPE
{
	SND_NONE,
	SND_CONVERSATIONAL,
	SND_SITREP,
	SND_DEATH_DAMAGE,
	SND_NUM_TYPES
};

enum SOUND_MODE
{
	SND_MODE_UNKNOWN,
	SND_MODE_EFX,
	SND_MODE_MUSIC,
	SND_MODE_DIALOG,
	SND_MODE_BANK_DEFINED
};

/* port: enumerator names unproven; the jukebox uses 0 = stealth music, 1 = fight music,
 * 2 and 3 = a given sound (CSndJukebox::Play 0x2f1380) */
enum MUSIC_MODE
{
	MODE_0,
	MODE_1,
	MODE_2,
	MODE_3,
	MODE_4,
	MODE_5,
	MODE_6,
	MODE_7,
	MODE_8,
	MODE_9
};

/* vagArchiveIsOpen, bnkArchiveIsOpen, snd_system_initialized and sound_map are
   file-local in zsnd_csnd.cpp (LOCAL symbols) */
/* port: sound_rdr removed - the binary's object is the LOCAL _sound_rdr in zsnd_csnd.cpp */

/* DWARF CSnd, 68 bytes (vptr +0x0). One entry of sounds.rdr: a bank sound (m_bank,
 * m_ID) or a streamed VAG (ST: N1/N2 names in VAGSTORE.ZAR). */
class CSnd
{
public:
	CSnd();

	static void Init();
	static void Open();
	static void Close();
	static void UIOpen();
	static void NetOpen();
	static void AddNewCSnd(CSnd* sound);
	static CSnd* GetSoundByName(const char* name);
	static bool GetSubtitles();
	static bool vagReadOffset(const char* name, u32& offset, u32& size);

	static bool PostTick(f32 dT, void* buf);

	void LoadCSnd(_zrdr* reader);
	int CalcVol(f32 dist, f32 volume); /* 0x2ec780: f12 = distance, f13 = volume; fptosi result */

	static zdb::CNode* m_listener; /* type: skeleton definition m_listener__4CSnd */

	static f32 m_fadetime;

	static u8* m_snd_data; /* port: unproven - not in the ELF (zsound_holding.cpp) */
	static u32 m_snd_len; /* port: unproven - not in the ELF (zsound_holding.cpp) */

	static s32 m_max_num_vags;

	static bool m_isDisabled;
	static bool m_bShowSubtitles;
	static bool m_hasreverb;
	static bool m_vagEnabled;
	static bool m_listenerIsValid;
	static zar::CZAR m_vagArchive;
	static zar::CZAR m_bnkArchive;
	static s32 m_bnkoffset;
	static s32 m_vagoffset;

	static std::unordered_map<const char*, CSnd*> m_soundmap; /* port: unproven - not in the ELF; the ELF's map is the LOCAL sound_map */
	static std::vector<u32> m_bankloaded; /* vector_pod<Ui>: 1 = the bank at that index loaded */
	static std::vector<u32> m_soundbank; /* vector_pod<Ui>: 989snd bank handles, by bank index */
	static std::vector<CSnd*> m_soundlist;
	/* DWARF members */
	f32 m_vol;

	char* m_name;

	PNT2D m_range; /* full volume up to x, silent from y (CalcVol) */

	s32 m_bank;
	s32 m_ID;

	bool m_isStreamed;
	bool m_isOneShot;
	bool m_isHeadsetStream;

	u8 m_soundmode; /* SOUND_MODE */
	u8 m_type; /* SOUND_TYPE */

	char* m_stream1name;
	char* m_stream2name;
	char* m_headsetstreamname;

	char* m_subtitle;
	CValve* m_subtitle_translator;
	f32 m_subtitle_time;

	s32 m_offset1;
	s32 m_offset2;
	/* @socom-skeleton decl 4CSnd */
public:
	virtual ~CSnd();
	virtual CSndInstance * PlaySound(CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySoundVol(float, CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySound3D(const CPnt3D *, float, int, CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySoundVolPanPitch(float, int, int, CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySound(bool, CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySoundVol(float, bool, CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySound3D(const CPnt3D *, bool, float, int, CSndInstance *, unsigned int);
	virtual CSndInstance * PlaySoundVolPanPitch(float, int, int, bool, CSndInstance *, unsigned int);
	static void Uninit();
	static void CleanupLoading();
	static void SetupSoundGroups();
	static void SetupJukebox(const char *);
	static int LoadSounds(const char *); /* returns the bank index (0x2edf50) */
	static int LoadSounds(const char *, const char *); /* returns the bank index (0x2edba0) */
	static bool LoadBank(const char *); /* 0x2ed910 returns true when the bank loaded */
	static void SetSubtitles(bool);
	void CalcVolPan(const CPnt3D *, float, int *, int *);
	int StreamSoundVolPan(int, int, CSndInstance *); /* 0x2ec4f0: -1 started, 0 not */
	static void UnloadAllSounds();
	static void OnListenerDeath();
	static void PlayErrorSound();
	static void WaitForCDRead(); /* static: 0x2ebf90 uses no this */
	static void SetReverbDepth(const float *); /* static: CMission::PreOpen 0x1f8d84 passes the float pointer in a0 */
	static void SetReverbSeconds(const float *); /* static: as SetReverbDepth (0x1f8dc0) */
	static void SetGroupVol(int, float);
	static void SetGroupVolTemp(float, float, int, int, int, int, int, int, int);
	static void ResetGroupVolTemp(); /* static: PostTick 0x2ec178 passes no object */
	static unsigned char m_DisplaySounds;
	static int m_curID;
	static int m_curbank;
	static unsigned char m_debugMusic;
	static CSnd* m_errorsound; /* 4 bytes: LoadSounds stores sound_map["SND_NEG"], PlayErrorSound calls it */
	static int m_fade_oldvol[7]; /* 28 bytes: group volumes saved by SetGroupVolTemp */
	static int m_fadegroup[7];
	static float m_fadepct;
	static CMatrix m_listenermatrix; /* 0x50e860, 64 B (was uchar[64]): the inverse listener matrix (PostTick) */
	static int m_num_sounds_playing;
	static int m_num_streams_used;
	/* @socom-skeleton end 4CSnd */
};

/* DWARF CSndInstance, 40 bytes, no base class: one playing (or pending) sound. m_handle
 * is the 989snd handle, -1 while a command waits for its answer, 0 once finished. */
class CSndInstance
{
public:
	static void InitInstancePool(s32 count);
	static void ReleaseSoundInstance(CSndInstance* instance);
	static void PauseAllSounds();

	void Stop();

	static bool m_allpaused;
	static f32 m_mastervol;
	static std::list<CSndInstance*> m_instancelist;
	static std::vector<CSndInstance*> m_sound_instance_pool;

	u32 m_handle;
	CSnd* m_parent;

	f32 m_vol;

	CPnt3D m_pos;

	bool m_is3D;
	bool m_forcedLoop;
	bool m_paused;
	bool m_terminateOnFinish;
	bool m_terminateASAP;
	bool m_pauseASAP;
	bool m_continueASAP;

	f32 m_fadeTime;
	u32 m_entityID;
	/* @socom-skeleton decl 12CSndInstance */
public:
	static void Cleanup();
	static CSndInstance * AcquireSoundInstance(unsigned int, CSnd *);
	void InitInstance(unsigned int, CSnd *);
	void SetVol(float);
	void SetPan(int);
	void SetPitch(int);
	void SetPos(const CPnt3D *);
	static void Remove(unsigned int, bool, bool);
	static void AwarenessUpgrade(unsigned int);
	static bool PostTick(float, void *); /* returns false (0x2efa5c) */
	bool Tick(float); /* true once the sound has ended */
	void FadeOut(float);
	bool IsFading();
	bool IsPlaying();
	void Set3D(float);
	void TerminateOnFinish();
	static void UIStopAllSounds(); /* static: 0x2ef540 uses no this (UIStopAllSounds__FP13C2DAnimCmdHdrPf passes none) */
	static void StopAllSounds();
	static void StopAllSounds(SOUND_MODE);
	static void ResumeAllSounds();
	static void Init();
	static void DebugSoundList();
	static void RemoveFromList(); /* static: 0x2ef010 uses no this */
	static void PlaySoundCallback(unsigned int, unsigned long);
	static std::vector<CSndInstance*> m_removallist; /* vector_pod<Ui> (12 bytes) */
	/* @socom-skeleton end 12CSndInstance */
};

/* port: no DWARF type; statics only. Mission music: weighted random sequences of streamed
 * music for stealth and fight, plus single sounds played on request (0x2f0fc0-0x2f1c90). */
class CSndJukebox
{
public:
	// Disallow construction of a static class
	CSndJukebox() = delete;
public:
	static void Start();
	static void Tick(f32 delta);
	static void Stop();

	static void Play(MUSIC_MODE mode, CSnd* sound);
	static void PlayRandom(MUSIC_MODE mode);

	static void IsInFight(bool inFight);

	static bool m_isinfight;
	/* port: m_weights/m_currentmode are the statics below (symbols m_weights__11CSndJukebox, m_currentmode__11CSndJukebox) */
	/* @socom-skeleton decl 11CSndJukebox */
public:
	static void Cleanup();
	static void LoadPlaylists(const char *);
	static void LoadMusicLists(_zrdr *, int);
	static void FadeOut();
	static void ClearQueue();
	static void NormalizeWeights(MUSIC_MODE); /* static: 0x2f1040 takes the mode in a0 */
	static signed char m_currentmode; /* MUSIC_MODE playing, -1 none */
	static CSndSequence* m_cursequence;
	static CSndInstance* m_cursound;
	static unsigned char m_jukebox_stopped;
	static std::vector<CSndSequence*> m_playlist[2]; /* 24 bytes: stealth (0) and fight (1) sequences */
	static unsigned char m_playlists_loaded;
	static struct Queued { CSnd* sound; signed char mode; } m_queue; /* 8 bytes: the request waiting for a fade */
	static std::vector<float> m_weights[2]; /* 24 bytes: the playlists' weights */
	/* @socom-skeleton end 11CSndJukebox */
};

/* @socom-skeleton decl 17CSndSequenceEntry */
/* port: no DWARF type; 16 bytes from the asm (0x2f1ea0, 0x2f1ef0) */
class CSndSequenceEntry
{
public:
	CSndSequenceEntry(CSnd *, float);
	bool Tick(float); /* true when the entry is over */
	void Play();
	void Stop();
	void FadeOut();
	bool IsFading();

	CSnd* m_sound;
	CSndInstance* m_instance; /* never set by the constructor (0x2f1fa0); see the .cpp */
	f32 m_pausetime; /* for an entry without a sound: the pause */
	f32 m_timer;
};
/* @socom-skeleton end 17CSndSequenceEntry */

/* port: no DWARF type; 24 bytes from the asm (0x2f2410, 0x2f2100): a list of sounds and
 * pauses the jukebox plays in order */
class CSndSequence
{
public:
	/* @socom-skeleton decl 12CSndSequence */
public:
	CSndSequence();
	~CSndSequence();
	void CreateSequence(_zrdr *);
	bool Tick(float); /* true once the sequence is over */
	bool IsFading();
	void FadeOut();
	void Play();
	void Stop();
	/* @socom-skeleton end 12CSndSequence */

	std::vector<CSndSequenceEntry> m_entries;
	s32 m_current; /* playing entry, -1 before the first */
	char* m_name;
	bool m_done;
	bool m_fading;
};

/* @socom-skeleton decl 9CSndGroup */
/* port: no DWARF type; members from the asm (0x2f05a0, 0x2f0a10): a CSnd that plays one
 * of its entries, picked by weight (96 bytes). */
class CSndGroup : public CSnd
{
public:
	CSndGroup() : m_dynamic_weights(0.0f) {} /* inline in LoadSoundGroups (0x2f0890) */
	virtual ~CSndGroup();
	virtual CSndInstance* PlaySound(CSndInstance *, unsigned int);
	virtual CSndInstance* PlaySoundVol(float, CSndInstance *, unsigned int);
	virtual CSndInstance* PlaySound3D(const CPnt3D *, float, int, CSndInstance *, unsigned int);
	virtual CSndInstance* PlaySoundVolPanPitch(float, int, int, CSndInstance *, unsigned int);
	static void LoadSoundGroups();
	void LoadCSndGroup(_zrdr *);
	void NormalizeWeights();

	std::vector<CSnd*> m_sounds; /* +0x44 */
	std::vector<f32> m_weights; /* +0x50 */
	f32 m_dynamic_weights; /* +0x5c: a played entry's weight is scaled by this */
};
/* @socom-skeleton end 9CSndGroup */
#endif
