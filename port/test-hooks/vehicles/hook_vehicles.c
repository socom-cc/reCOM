/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): skip CMission::LoadVehicles (no seals are created,
 * so the player chain owned by the other worker is bypassed) to see how far mission start and
 * the first world frames get through the real render path. Linked only into boot-render2-hook. */
int __wrap__ZN8CMission12LoadVehiclesEj(void *self, unsigned int arg)
{
    (void)self; (void)arg;
    return 1;
}
