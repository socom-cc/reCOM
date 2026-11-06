/* Port compatibility header: declarations the game source takes from the SCE-RT
 * Medius lobby client library. The original header name is unknown: `medius.h` is a
 * port guess. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. The online layer is stubbed offline later; these exist so the
 * declarations in src compile. */
#ifndef SOCOM_COMPAT_MEDIUS_H
#define SOCOM_COMPAT_MEDIUS_H

/* By value in the lobby callbacks, e.g. cbGetMyClans__F15MediusErrorCode15MediusErrorCode
 * 15MediusErrorCodeP24MediusGetMyClansResponse and
 * LookupMediusCallbackStatus__F20MediusCallbackStatus. Enumerators unknown:
 * port: unproven. */
enum MediusErrorCode {};
enum MediusCallbackStatus {};

#endif /* SOCOM_COMPAT_MEDIUS_H */
