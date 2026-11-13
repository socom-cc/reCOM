/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): zdb::CMesh::Clone 0x30f330 and CMesh::AddLOD 0x30f7b0
 * belong to the render worker and currently fault on the seal model mesh (its LOD chain is NULL).
 * Clone returns the source mesh (shared, not copied) and AddLOD does nothing, so the boot can show
 * what runs after them. Linked only into the boot-player3-hook build. */
void *__wrap__ZN3zdb5CMesh5CloneEv(void *self)
{
    return self;
}

void __wrap__ZN3zdb5CMesh6AddLODEPS0_f(void *self, void *lod, float range)
{
    (void)self; (void)lod; (void)range;
}
