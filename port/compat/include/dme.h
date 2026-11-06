/* Port compatibility header: declarations the game source takes from the SCE-RT
 * Medius DME library ("dme version: 1.16.S033", string at 0x43e1f8; C API such as
 * NetCreateObject at 0x41cb18). The original header name is unknown: `dme.h` is a
 * port guess. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. The online layer is stubbed offline later; these exist so the
 * declarations in src compile. */
#ifndef SOCOM_COMPAT_DME_H
#define SOCOM_COMPAT_DME_H

/* Passed by value in one GPR word (CZNetwork::zNetCreateObject 0x321860 forwards
 * a2/a3 to NetCreateObject; CZBroadcastSchedule::CZBroadcastSchedule 0x322300 stores
 * a2 with sw). Enumerators unknown: port: unproven. */
enum NetOwnershipStatus {};
enum NetObjectLifespan {};
enum NetThresholdMethod {};

/* By value in cbDMENetPingCallback__F12NetErrorCodePcUi (zNetMedius.cpp). Enumerators
 * unknown: port: unproven. */
enum NetErrorCode {};

#endif /* SOCOM_COMPAT_DME_H */
