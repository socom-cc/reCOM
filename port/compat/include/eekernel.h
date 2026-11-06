/* Port compatibility header: the Sony EE eekernel.h. ps2sdk's kernel.h declares the
 * EE kernel calls the game uses (DIntr, EIntr, AddDmacHandler, EnableIntc,
 * ChangeThreadPriority, GetThreadId, alarms, semaphores, threads) under the same
 * names and arguments, so this header maps straight onto it. Shared and
 * append-only: add declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_EEKERNEL_H
#define SOCOM_COMPAT_EEKERNEL_H

#include <kernel.h>

/* Sony's semaphore parameter block (CMission::Init 0x1f9038 fills maxCount at +4,
 * initCount at +8, option at +0x14): the same layout as ps2sdk's ee_sema_t. */
struct SemaParam
{
    int currentCount;
    int maxCount;
    int initCount;
    int numWaitThreads;
    u32 attr;
    u32 option;
};
#ifdef __cplusplus
static inline s32 CreateSema(struct SemaParam *param) { return CreateSema((ee_sema_t *)param); }
static inline s32 ReferSemaStatus(s32 sema_id, struct SemaParam *param) { return ReferSemaStatus(sema_id, (ee_sema_t *)param); }
#endif

/* Sony's thread parameter block (CGame::Tick 0x20b1e4 fills entry +4, stack +8, stackSize
 * +0xc, gpReg +0x10, initPriority +0x14, option +0x20): ps2sdk's ee_thread_t layout. */
struct ThreadParam
{
    int status;
    void *entry;
    void *stack;
    int stackSize;
    void *gpReg;
    int initPriority;
    int currentPriority;
    u32 attr;
    u32 option;
};
#ifdef __cplusplus
static inline s32 CreateThread(struct ThreadParam *param) { return CreateThread((ee_thread_t *)param); }
#endif

#endif /* SOCOM_COMPAT_EEKERNEL_H */
