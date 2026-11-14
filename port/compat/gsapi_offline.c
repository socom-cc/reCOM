/* Functional port lane: offline voice-recognition provider (the gsapi speech library the
 * game links for recoTick is not available). Not provider code; nothing here is
 * evidence for the matching lane. The port never sets recoInited, so this is only
 * linked, never called. */
int gsapi_ExecServer(void *ctx)
{
    (void)ctx;
    return 0;
}

/* The rest of the provider calls reco.cpp makes (recoSetupLanguage, recoEnableWord, the
 * result callback): each answers "provider unavailable" (-1, an empty result string), so
 * recognition never starts and recoInited stays 0. */
struct GSAPI_WORD_LIST { int count; int *ids; };

int gsapi_GetResultString(void *engine, unsigned int id, char **text)
{
    (void)engine; (void)id;
    if (text) *text = 0;
    return -1;
}

const char *gsapi_ErrorGetString(int error)
{
    (void)error;
    return "gsapi: voice recognition is offline in the port";
}

int gsapi_EngineEnableWords(void *engine, struct GSAPI_WORD_LIST words) { (void)engine; (void)words; return -1; }
int gsapi_EngineDisableAllWords(void *engine) { (void)engine; return -1; }
int gsapi_EngineStop(void *engine) { (void)engine; return -1; }
int gsapi_LanguageLoadBuffer(void *data, int flags) { (void)data; (void)flags; return -1; }
int gsapi_EngineOpen(int flags, void **engine) { (void)flags; if (engine) *engine = 0; return -1; }
int gsapi_NotifySetCallback(void *callback) { (void)callback; return -1; }
int gsapi_EngineSetMode(void *engine, int mode) { (void)engine; (void)mode; return -1; }
