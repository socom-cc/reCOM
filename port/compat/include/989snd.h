/* Port compatibility header: the 989snd EE client library the game calls (header name
 * unproven). Implemented in port/compat/snd989.c as an RPC client of the disc's
 * 989SND.IRX; prototypes follow the ELF's argument packing (0x2ea400-0x2ebd20) and the
 * game's call sites. Argument names are descriptive, not Sony's. Shared and
 * append-only: add declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_989SND_H
#define SOCOM_COMPAT_989SND_H

#include <libcdvd.h> /* sceCdRMode */

#ifdef __cplusplus
extern "C" {
#endif

/* Completion callback of a queued command: the IOP's result and the caller's word
 * (CSndInstance::PlaySoundCallback stores a sound handle into the instance). */
typedef void (*SndCompleteProc)(unsigned int result, unsigned long user);

/* CD access that cooperates with 989snd streaming (0x2ea6d0 / 0x2ea630 / 0x2ea600).
 * With streaming not initialised they are sceCdRead / sceCdSync / sceCdGetError. */
int snd_StreamSafeCdRead(unsigned int lsn, unsigned int sectors, void *buf, sceCdRMode *mode);
int snd_StreamSafeCdSync(int mode);
int snd_StreamSafeCdGetError(void);

/* Sound-system start and set-up the game calls from CSnd::Init (0x2ee2c4-0x2ee31c) and
 * CSnd::UIOpen (0x2ee124). */
int snd_StartSoundSystem(void);
void snd_SetReverbType(int core, int type);
void snd_AutoReverb(int core, int depth, int time, int channels);
int snd_InitVAGStreamingEx(int streams, int buffer_size, int a2, int a3);

/* Stop one playing sound by handle (CSndInstance::UIStopAllSounds 0x2ef5a8). */
void snd_StopSound(unsigned int handle);

/* RPC transport (0x2eaaa0, 0x2eae30, 0x2eb7f0) and command caching (0x2eaa90, 0x2eaa80). */
void snd_SendIOPCommandNoWait(int command, int size, char *data, SndCompleteProc proc, unsigned long user);
int snd_SendIOPCommandAndWait(int command, int size, char *data);
int snd_FlushSoundCommands(void);
void snd_StartCaching(void);
int snd_SendCache(void);
int snd_StopSoundSystem(void);

/* Banks: handle 0 = failure (0x2eb6b0, 0x2eb540, 0x2eb520, 0x2eb4f0). */
int snd_BankLoad(const char *name, int offset);
int snd_BankLoadByLoc(int sector, int offset);
void snd_ResolveBankXREFS(void);
void snd_UnloadBank(int bank);

/* Volume groups (0x2eb4b0 / 0x2eb480) and output mode (0x2eb450 / 0x2eb440). */
void snd_SetMasterVolume(int group, int volume);
int snd_GetMasterVolume(int group);
void snd_SetPlaybackMode(int mode);
int snd_GetPlaybackMode(void);

/* Sounds (0x2eb3a0 .. 0x2eb1d0). The game passes pan -1 (plays) and -2 (CSndInstance::SetVol);
 * pan is otherwise 0..359 degrees, volume 0..1024. Meaning of -1/-2 unproven. */
void snd_PlaySoundVolPanPMPB_CB(int bank, int sound, int volume, int pan, int pitch_mod, int pitch_bend,
    SndCompleteProc proc, unsigned long user);
void snd_PlaySoundVolPanPMPB_A(int bank, int sound, int volume, int pan, int pitch_mod, int pitch_bend);
void snd_PauseSound(unsigned int handle);
void snd_ContinueSound(unsigned int handle);
void snd_SoundIsStillPlaying_CB(unsigned int handle, SndCompleteProc proc, unsigned long user);
void snd_SetSoundVolPan(unsigned int handle, int volume, int pan);
void snd_SetSoundPitch(unsigned int handle, int pitch);
void snd_SetSoundParams_CB(unsigned int handle, int mask, int volume, int pan, int pitch_mod, int pitch_bend,
    SndCompleteProc proc, unsigned long user);
void snd_AutoVol(unsigned int handle, int volume, int time, int mode);

/* VAG streaming (0x2ea850, 0x2ea930, 0x2ea7e0, 0x2ea7b0). */
void snd_CloseVAGStreaming(void);
void snd_StopAllStreams(void);
void snd_PlayVAGStreamByLoc_CB(int loc1, int loc2, int offset1, int offset2, int volume, int pan, int vol_group,
    int a7, int a8, SndCompleteProc proc, unsigned long user);
int snd_StreamSafeCheckCDIdle(int wait);

/* MPEG audio (0x2ea540 .. 0x2ea4e0) and calls into other IOP modules (0x2ea4a0 ..). */
int snd_InitMovieSound(int a0, int a1, int a2, int a3);
int snd_CloseMovieSound(void);
int snd_ResetMovieSound(void);
int snd_StartMovieSound(int a0, int a1, int a2);
int snd_GetTransStatus(void);
int snd_DoExternCall(int a0, int a1, int a2, int a3, int a4, int a5, int a6);
void snd_DoExternCall_A(int a0, int a1, int a2, int a3, int a4, int a5, int a6);
void snd_DoExternCall_CB(int a0, int a1, int a2, int a3, int a4, int a5, int a6, SndCompleteProc proc, unsigned long user);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_989SND_H */
