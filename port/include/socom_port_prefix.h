/* Forced-include prefix for the GCC functional port (port lane only).
 *
 * Metrowerks builds supplied common declarations through a prefix file. The
 * port supplies the GCC equivalents here instead of editing shared src/ files.
 * Nothing in this header is evidence for the matching lane. */
#ifndef SOCOM_PORT_PREFIX_H
#define SOCOM_PORT_PREFIX_H

#include <stddef.h>
#include <stdint.h>

/* Boot-milestone trace to the EE console (port/compat/port_diag.c). Compiles to
 * nothing unless SOCOM_PORT_TRACE_ON is defined. The Metrowerks lane never sees
 * this prefix, so src/ uses it only inside `#ifdef SOCOM_PORT`. */
#ifdef SOCOM_PORT_TRACE_ON
#ifdef __cplusplus
extern "C"
#endif
void socom_port_trace(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define SOCOM_PORT_TRACE(...) socom_port_trace(__VA_ARGS__)
#else
#define SOCOM_PORT_TRACE(...) ((void)0)
#endif

#endif /* SOCOM_PORT_PREFIX_H */
