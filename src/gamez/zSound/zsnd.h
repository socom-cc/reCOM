#ifndef ZSOUND_H
#define ZSOUND_H

#include <vector>
#include <unordered_map>

#include "gamez/zArchive/zar.h"
#include "gamez/zMath/zmath.h"
#include "gamez/zReader/zrdr.h"
#include "gamez/zSystem/zsys.h"
#include "gamez/zValve/zvalve.h"

class CSnd;
class CSndInstance;

namespace zdb
{
	class CNode;
}

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
	float CalcVol(f32 volume, f32 masterVolume);
	void SetupJukebox();

	static zdb::CNode* m_listener; /* type: skeleton definition m_listener__4CSnd */

	static f32 m_fadetime;

	static u8* m_snd_data;
	static u32 m_snd_len;
	
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

	static std::unordered_map<const char*, CSnd*> m_soundmap;
	static std::vector<CSnd*> m_bankloaded;
	static std::vector<CSnd*> m_soundbank;
	static std::vector<CSnd*> m_soundlist;
protected:
	f32 m_vol;

	char* m_name;

	PNT2D m_range;

	s32 m_bank;
	s32 m_ID;

	bool m_isStreamed;
	bool m_isOneShot;
	bool m_isHeadsetStream;

	u32 m_soundmode;
	u32 m_type;

	char* m_stream1name;
	char* m_stream2name;

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
	static void LoadSounds(const char *);
	static void LoadSounds(const char *, const char *);
	static void LoadBank(const char *);
	static void SetSubtitles(bool);
	void CalcVolPan(const CPnt3D *, float, int *, int *);
	void StreamSoundVolPan(int, int, CSndInstance *);
	static void UnloadAllSounds();
	static void OnListenerDeath();
	static void PlayErrorSound();
	void WaitForCDRead();
	static void SetReverbDepth(const float *); /* static: CMission::PreOpen 0x1f8d84 passes the float pointer in a0 */
	static void SetReverbSeconds(const float *); /* static: as SetReverbDepth (0x1f8dc0) */
	static void SetGroupVol(int, float);
	static void SetGroupVolTemp(float, float, int, int, int, int, int, int, int);
	void ResetGroupVolTemp();
	static unsigned char m_DisplaySounds;
	static int m_curID;
	static int m_curbank;
	static unsigned char m_debugMusic;
	static int m_errorsound;
	static unsigned char m_fade_oldvol[28];
	static int m_fadegroup[7];
	static float m_fadepct;
	static unsigned char m_listenermatrix[64];
	static int m_num_sounds_playing;
	static int m_num_streams_used;
	/* @socom-skeleton end 4CSnd */
};

class CSndInstance : public CSnd
{
public:
	static void InitInstancePool(s32 count);
	static void ReleaseSoundInstance(CSndInstance* instance);
	static void PauseAllSounds();

	void Stop();

	static bool m_allpaused;
	static f32 m_mastervol;
	static std::list<CSndInstance*> m_instancelist;
	static std::vector<CSnd*> m_sound_instance_pool;
	
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
	static void PostTick(float, void *);
	void Tick(float);
	void FadeOut(float);
	void IsFading();
	void IsPlaying();
	void Set3D(float);
	void TerminateOnFinish();
	static void UIStopAllSounds(); /* static: 0x2ef540 uses no this (UIStopAllSounds__FP13C2DAnimCmdHdrPf passes none) */
	static void StopAllSounds();
	static void StopAllSounds(SOUND_MODE);
	static void ResumeAllSounds();
	static void Init();
	static void DebugSoundList();
	void RemoveFromList();
	static void PlaySoundCallback(unsigned int, unsigned long);
	static int m_removallist[3];
	/* @socom-skeleton end 12CSndInstance */
};

class CSndJukebox
{
public:
	// Disallow construction of a static class
	CSndJukebox() = delete;
public:
	static void Cleanup();
	CRdrFile* LoadPlaylists();
	static void LoadMusicLists();

	static void Start();
	static void Tick(f32 delta);
	static void Stop();

	static void Play(MUSIC_MODE mode, CSnd* sound);
	static void PlayRandom(MUSIC_MODE mode);
	
	static void NormalizeWeights();

	static void IsInFight(bool inFight);
	
	static bool m_isinfight;
	/* port: m_weights/m_currentmode are the statics below (symbols m_weights__11CSndJukebox, m_currentmode__11CSndJukebox) */
	/* @socom-skeleton decl 11CSndJukebox */
public:
	static void LoadPlaylists(const char *);
	static void LoadMusicLists(_zrdr *, int);
	static void FadeOut();
	static void ClearQueue();
	void NormalizeWeights(MUSIC_MODE);
	static signed char m_currentmode;
	static int m_cursequence;
	static int m_cursound;
	static unsigned char m_jukebox_stopped;
	static unsigned char m_playlist[24];
	static unsigned char m_playlists_loaded;
	static unsigned char m_queue[8];
	static unsigned char m_weights[24];
	/* @socom-skeleton end 11CSndJukebox */
};

class CSndSequence
{
public:
	void CreateSequence(u32* param_1, s64 param_2);
	void Play();
	void Play(int** param_1);
	void Tick();
	void Stop();
	/* @socom-skeleton decl 12CSndSequence */
public:
	CSndSequence();
	~CSndSequence();
	void CreateSequence(_zrdr *);
	void Tick(float);
	void IsFading();
	void FadeOut();
	/* @socom-skeleton end 12CSndSequence */
};

/* @socom-skeleton decl 9CSndGroup */
class CSndGroup : public CSnd
{
public:
	virtual ~CSndGroup();
	virtual CSndInstance* PlaySound(CSndInstance *, unsigned int);
	virtual CSndInstance* PlaySoundVol(float, CSndInstance *, unsigned int);
	virtual CSndInstance* PlaySound3D(const CPnt3D *, float, int, CSndInstance *, unsigned int);
	virtual CSndInstance* PlaySoundVolPanPitch(float, int, int, CSndInstance *, unsigned int);
	static void LoadSoundGroups();
	void LoadCSndGroup(_zrdr *);
	void NormalizeWeights();
};
/* @socom-skeleton end 9CSndGroup */
/* @socom-skeleton decl 17CSndSequenceEntry */
class CSndSequenceEntry
{
public:
	CSndSequenceEntry(CSnd *, float);
	void Tick(float);
	void Play();
	void Stop();
	void FadeOut();
	void IsFading();
};
/* @socom-skeleton end 17CSndSequenceEntry */
#endif