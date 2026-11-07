/* Functional port lane: offline voice-recognition provider (the gsapi speech library the
 * game links for recoTick is not available). Not provider code; nothing here is
 * evidence for the matching lane. The port never sets recoInited, so this is only
 * linked, never called. */
int gsapi_ExecServer(void *ctx)
{
    (void)ctx;
    return 0;
}
