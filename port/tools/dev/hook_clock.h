/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. Its results are behaviour checks, never matching evidence. */
/* hook_clock.h (socom-port-limiter): the hooks' time base, the one the fake pad scripts use
 * (port/compat/libpad.c; a fake-pad build is required, and every build.sh has a default pad script).
 *  hook_fields()   60 Hz fields (vertical blanks) since scePadInit: real time, whatever the frame rate
 *                  (the missions run at the ELF's 30 fps cap; the menus at 30 before the first mission
 *                  and 60 after it, as the ELF).
 *  hook_ticks()    fields / 2, a 30 Hz clock. The hooks' delays were tuned in pad reads when the game
 *                  ran at 60 fps and read the pad 30 times a second; a tick is that much time, so the
 *                  old numbers keep their meaning.
 *  hook_step(&clock)  call once per pad read where a hook counted reads: returns the ticks since
 *                  the previous call (the first call and a read faster than a tick return 1; at most
 *                  <max>, default 4: while the game reads no pad - a load - no time counts, as no
 *                  reads counted before). Write `g_reads += hook_step(&g_clock);`; code that tests exact
 *                  values (t == 30, t % 60 == 0) runs once per tick instead:
 *                  `for (n = hook_step(&g_clock); n > 0; n--) { g_reads++; per_tick(); }`.
 *  hook_field_step(&clock)  the same in fields for hooks that counted game frames (below).
 *  hook_anchor(name, k)  the field of the k-th time the game reached a fake-pad anchor (menu, core,
 *                  play, ...: port/test/fake_pad_anchors.cpp), -1 while it has not;
 *                  hook_set_anchor(name) names a point of the hook's own for its pad script. */
#ifndef HOOK_CLOCK_H
#define HOOK_CLOCK_H

extern "C" unsigned int socom_fake_fields(void);
extern "C" int socom_fake_anchor_field(const char *name, unsigned int k);
extern "C" void socom_fake_anchor(const char *name);

static inline unsigned int hook_fields() { return socom_fake_fields(); }
static inline unsigned int hook_ticks() { return socom_fake_fields() / 2; }
static inline int hook_anchor(const char *name, unsigned int k = 1) { return socom_fake_anchor_field(name, k); }
static inline void hook_set_anchor(const char *name) { socom_fake_anchor(name); }

static inline unsigned int hook_step(unsigned int *clock, unsigned int max = 4)
{
    unsigned int now = hook_ticks() + 1; /* *clock 0: not started */
    unsigned int before = *clock;

    if (before == 0)
    {
        *clock = now;
        return 1;
    }

    *clock = now > before ? now : before + 1;
    return *clock - before < max ? *clock - before : max;
}

/* hook_field_step(&clock): for hooks that counted game frames (tuned at 60 fps, a frame a field):
 * the fields since the previous call, 0 when none has passed (a second call in the same frame); the
 * first call returns 1. Run the per-frame code once per field it returns:
 * `for (n = hook_field_step(&g_fclock); n > 0; n--) { frame++; per_frame(); }`. At the 30 fps cap
 * that is twice per game frame. At most <max> (default 4) per call: a gap without calls (a pause,
 * the full-screen map, a load) does not count, as no frames were counted there before either. */
static inline unsigned int hook_field_step(unsigned int *clock, unsigned int max = 4)
{
    unsigned int now = hook_fields() + 1; /* *clock 0: not started */
    unsigned int before = *clock;

    if (before == 0)
    {
        *clock = now;
        return 1;
    }

    *clock = now > before ? now : before;
    return *clock - before < max ? *clock - before : max;
}
#endif
