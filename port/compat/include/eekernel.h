/* Port compatibility header: the Sony EE eekernel.h. ps2sdk's kernel.h declares the
 * EE kernel calls the game uses (DIntr, EIntr, AddDmacHandler, EnableIntc,
 * ChangeThreadPriority, GetThreadId, alarms, semaphores, threads) under the same
 * names and arguments, so this header maps straight onto it. Shared and
 * append-only: add declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_EEKERNEL_H
#define SOCOM_COMPAT_EEKERNEL_H

#include <kernel.h>

#endif /* SOCOM_COMPAT_EEKERNEL_H */
