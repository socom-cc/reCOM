/* Port compatibility header: the SDK's network-configuration interface (libnetcnfif) types the
 * game source uses (CNetCnf in zNetwork, the UINet* UI commands in zAnim). Only the members the
 * game touches are relied on; their offsets are the ones those commands read and write
 * (UINetSaveIfc 0x1d1400, UINetSaveCombo 0x1d0ec0, UINetGetIFCInfo 0x1d0f90). Member names follow
 * the SDK's libnetcnfif; ps2sdk has no such header. Online only: the port never runs them. */
#ifndef SOCOM_COMPAT_NETCNFIF_H
#define SOCOM_COMPAT_NETCNFIF_H

/* a configuration file of a list (520 bytes) */
typedef struct sceNetcnfifList
{
    int type;               /* +0x0 */
    int stat;               /* +0x4 */
    char sys_name[256];     /* +0x8 the file name */
    char usr_name[256];     /* +0x108 the display name */
} sceNetcnfifList;

/* the editable settings of an interface / device / combination (UINetSaveIfc, UINetSaveCombo) */
typedef struct sceNetcnfifData
{
    char attach_ifc[256];       /* +0x0 */
    char attach_dev[256];       /* +0x100 */
    char dhcp_host_name[256];   /* +0x200 */
    char address[256];          /* +0x300 */
    char netmask[256];          /* +0x400 */
    char gateway[256];          /* +0x500 */
    char dns1_address[256];     /* +0x600 */
    char dns2_address[256];     /* +0x700 */
    char phone_numbers1[256];   /* +0x800 */
    char phone_numbers2[256];   /* +0x900 */
    char phone_numbers3[256];   /* +0xa00 */
    char auth_name[256];        /* +0xb00 */
    char auth_key[256];         /* +0xc00 */
    char peer_name[256];        /* +0xd00 */
    char vendor[256];           /* +0xe00 */
    char product[256];          /* +0xf00 */
    char chat_additional[256];  /* +0x1000 */
    char outside_number[256];   /* +0x1100 */
    char outside_delay[256];    /* +0x1200 */
    int ifc_type;               /* +0x1300 */
    int mtu;                    /* +0x1304 */
    int ifc_idle_timeout;       /* +0x1308 */
    int dev_type;               /* +0x130c */
    int phy_config;             /* +0x1310 */
    int dialing_type;           /* +0x1314 */
    int dev_idle_timeout;       /* +0x1318 */
    int p0;                     /* +0x131c */
    unsigned char dhcp;         /* +0x1320 */
    unsigned char dns1_nego;    /* +0x1321 */
    unsigned char dns2_nego;    /* +0x1322 */
    unsigned char f_auth;       /* +0x1323 */
    unsigned char auth;         /* +0x1324 */
    unsigned char pppoe;        /* +0x1325 */
    unsigned char prc_nego;     /* +0x1326 */
    unsigned char acc_nego;     /* +0x1327 */
    unsigned char accm_nego;    /* +0x1328 */
    unsigned char p1;
    unsigned char p2;
    unsigned char p3;
    int p4[5];
} sceNetcnfifData;

/* The result of a request (sceNetcnfifGetResult): CNetCnf's states read `data` (the count, the
 * entry or a negative netcnf error, SignalNetCnfError 0x401270) and `addr` (the IOP work area,
 * sceNetcnfifGetAddr; the GetAddr states read +0xc). The 784-byte stack copies in the ELF fit the
 * SDK's member list; only `data` and `addr` are relied on. */
typedef struct sceNetcnfifArg
{
    int data;                 /* +0x0 */
    int f_no_decode;          /* +0x4 */
    int type;                 /* +0x8 */
    int addr;                 /* +0xc */
    char fname[256];          /* +0x10 */
    char usr_name[256];       /* +0x110 */
    char new_usr_name[256];   /* +0x210 */
} sceNetcnfifArg;

/* libnetcnfif's EE calls (ELF 0x425280..0x425e78, provider code; the port's offline stand-ins are
 * in port/compat/netcnfif_offline.c). Requests start an IOP call; sceNetcnfifCheck answers nonzero
 * while it runs, then sceNetcnfifGetResult gives its result. Prototypes from the CNetCnf call
 * sites (zNetCnf.cpp) and the SDK's names. */
#ifdef __cplusplus
extern "C" {
#endif
void sceNetcnfifInit(void);
void sceNetcnfifSetup(void);
int sceNetcnfifCheck(void);
void sceNetcnfifGetResult(sceNetcnfifArg *result);
void sceNetcnfifGetCount(const char *fname, int type);
void sceNetcnfifGetList(const char *fname, int type, sceNetcnfifList *list, int count);
void sceNetcnfifLoadEntry(const char *fname, int type, const char *usr_name, sceNetcnfifData *data);
void sceNetcnfifAddEntry(const char *fname, int type, const char *usr_name);
void sceNetcnfifDeleteAll(const char *fname);
void sceNetcnfifAllocWorkarea(int size);
void sceNetcnfifFreeWorkarea(void);
void sceNetcnfifGetAddr(void);
int sceNetcnfifSendIOP(unsigned int data, unsigned int addr, unsigned int size);
int sceNetcnfifDmaCheck(int id);
void sceNetcnfifDataInit(sceNetcnfifData *data);
void sceNetcnfifDataDump(sceNetcnfifData *data);
#ifdef __cplusplus
}
#endif

#endif
