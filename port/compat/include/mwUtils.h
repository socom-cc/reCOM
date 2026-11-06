/* Port compatibility header: the Metrowerks PS2 runtime mwUtils.h (C linkage; the
 * ELF symbol is the plain C name mwInit). Shared and append-only. */
#ifndef SOCOM_COMPAT_MWUTILS_H
#define SOCOM_COMPAT_MWUTILS_H

#ifdef __cplusplus
extern "C" {
#endif

/* 0x144890: __initialize_cpp_rts over the static-initialiser and exception tables. */
void mwInit(void);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_MWUTILS_H */
