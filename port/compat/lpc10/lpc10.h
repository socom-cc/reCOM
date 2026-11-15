/* Functional port lane: the LPC-10 (FS-1015) 2400 bit/s voice codec of the push-to-talk client
 * library (libpttclient, a PROVIDER: DWARF compile units C:\dev\libpttclient\*.c). Not game source;
 * nothing here is evidence for the matching lane.
 *
 * Written from the reference ELF (code 0x3eb3a0..0x3efed4 and 0x3f1380..0x3f6918, tables in .data
 * 0x43c3f0..0x43d318, docs/port/notes/lpc10.md). The library is the f2c translation of the
 * reference coder, with its Fortran SAVE variables moved into the two state records below; the
 * f2c shapes (pointer parameters for scalars, 1-based index adjustments) are kept as the ELF has
 * them. In the ELF the units were compiled as C++ (cfront-style mangled names such as
 * lpc10_encode__FPfPiP19lpc10_encoder_state); nothing in the game calls them by those names (the
 * only callers are PTT_Init / PTT_Heartbeat, offline stand-ins in port/compat/ptt_offline.cpp), so
 * the port gives them C linkage under their plain names.
 *
 * One frame: 180 samples of 8 kHz speech (floats, full scale +-1) <-> 54 bits (one int each). */
#ifndef SOCOM_PORT_LPC10_H
#define SOCOM_PORT_LPC10_H

#include <stdlib.h>
#include <math.h>

#ifdef __GNUC__
/* The ELF keeps every multiply and add separate (mul.s then add.s / sub.s): no fused forms. */
#pragma GCC optimize("fp-contract=off")
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* f2c types as the ELF's DWARF has them: integer and logical are 32-bit int, real is float. */
typedef int integer;
typedef int logical;
typedef float real;
typedef double doublereal;
typedef short shortint;

#define TRUE_ (1)
#define FALSE_ (0)

/* f2c.h macros (the ELF's abs of a real tests x < 0 and negates; same values) */
#ifndef __cplusplus
#undef abs
#define abs(x) ((x) >= 0 ? (x) : -(x))
#undef min
#define min(a, b) ((a) <= (b) ? (a) : (b))
#undef max
#define max(a, b) ((a) >= (b) ? (a) : (b))
#endif

/* DWARF lpc10_encoder_state, 9540 bytes (analys.c CU) */
struct lpc10_encoder_state {
    /* hp100 */
    real z11;               /* +0x0000 */
    real z21;               /* +0x0004 */
    real z12;               /* +0x0008 */
    real z22;               /* +0x000c */
    /* analys */
    real inbuf[540];        /* +0x0010 */
    real pebuf[540];        /* +0x0880 */
    real lpbuf[696];        /* +0x10f0 */
    real ivbuf[312];        /* +0x1bd0 */
    real bias;              /* +0x20b0 */
    integer osbuf[10];      /* +0x20b4 */
    integer osptr;          /* +0x20dc */
    integer obound[3];      /* +0x20e0 */
    integer vwin[6];        /* +0x20ec, was [2][3] */
    integer awin[6];        /* +0x2104, was [2][3] */
    integer voibuf[8];      /* +0x211c, was [2][4] */
    real rmsbuf[3];         /* +0x213c */
    real rcbuf[30];         /* +0x2148, was [10][3] */
    real zpre;              /* +0x21c0 */
    /* onset */
    real n;                 /* +0x21c4 */
    real d__;               /* +0x21c8 */
    real fpc;               /* +0x21cc */
    real l2buf[16];         /* +0x21d0 */
    real l2sum1;            /* +0x2210 */
    integer l2ptr1;         /* +0x2214 */
    integer l2ptr2;         /* +0x2218 */
    integer lasti;          /* +0x221c */
    logical hyst;           /* +0x2220 */
    /* voicin */
    real dither;            /* +0x2224 */
    real snr;               /* +0x2228 */
    real maxmin;            /* +0x222c */
    real voice[6];          /* +0x2230, was [2][3] */
    integer lbve;           /* +0x2248 */
    integer lbue;           /* +0x224c */
    integer fbve;           /* +0x2250 */
    integer fbue;           /* +0x2254 */
    integer ofbue;          /* +0x2258 */
    integer sfbue;          /* +0x225c */
    integer olbue;          /* +0x2260 */
    integer slbue;          /* +0x2264 */
    /* dyptrk */
    real s[60];             /* +0x2268 */
    integer p[120];         /* +0x2358, was [2][60] */
    integer ipoint;         /* +0x2538 */
    real alphax;            /* +0x253c */
    /* chanwr */
    integer isync;          /* +0x2540 */
};

/* DWARF lpc10_decoder_state, 3072 bytes (bsynz.c CU) */
struct lpc10_decoder_state {
    /* decode */
    integer iptold;         /* +0x0000 */
    logical first;          /* +0x0004 */
    integer ivp2h;          /* +0x0008 */
    integer iovoic;         /* +0x000c */
    integer iavgp;          /* +0x0010 */
    integer erate;          /* +0x0014 */
    integer drc[30];        /* +0x0018, was [3][10] */
    integer dpit[3];        /* +0x0090 */
    integer drms[3];        /* +0x009c */
    /* synths */
    real buf[360];          /* +0x00a8 */
    integer buflen;         /* +0x0648 */
    /* pitsyn */
    integer ivoico;         /* +0x064c */
    integer ipito;          /* +0x0650 */
    real rmso;              /* +0x0654 */
    real rco[10];           /* +0x0658 */
    integer jsamp;          /* +0x0680 */
    logical first_pitsyn;   /* +0x0684 */
    /* bsynz */
    integer ipo;            /* +0x0688 */
    real exc[166];          /* +0x068c */
    real exc2[166];         /* +0x0924 */
    real lpi1;              /* +0x0bbc */
    real lpi2;              /* +0x0bc0 */
    real lpi3;              /* +0x0bc4 */
    real hpi1;              /* +0x0bc8 */
    real hpi2;              /* +0x0bcc */
    real hpi3;              /* +0x0bd0 */
    real rmso_bsynz;        /* +0x0bd4 */
    /* random */
    integer j;              /* +0x0bd8 */
    integer k;              /* +0x0bdc */
    shortint y[5];          /* +0x0be0 */
    /* deemp */
    real dei1;              /* +0x0bec */
    real dei2;              /* +0x0bf0 */
    real deo1;              /* +0x0bf4 */
    real deo2;              /* +0x0bf8 */
    real deo3;              /* +0x0bfc */
};

#ifndef __cplusplus
_Static_assert(sizeof(struct lpc10_encoder_state) == 9540, "lpc10_encoder_state size");
_Static_assert(sizeof(struct lpc10_decoder_state) == 3072, "lpc10_decoder_state size");
#endif

/* common /contrl/ (0x5754d0, 12 bytes; set by lpcini_) */
struct lpc10_contrl {
    integer order;
    integer lframe;
    logical corrp;
};
extern struct lpc10_contrl contrl_;

/* public interface (lpcenc.c, lpcdec.c, lpcini.c) */
int lpc10_encode(real *speech, integer *bits, struct lpc10_encoder_state *st);
int lpc10_decode(integer *bits, real *speech, struct lpc10_decoder_state *st);
int lpcini_(void);
struct lpc10_encoder_state *create_lpc10_encoder_state(void);
void init_lpc10_encoder_state(struct lpc10_encoder_state *st);
struct lpc10_decoder_state *create_lpc10_decoder_state(void);
void init_lpc10_decoder_state(struct lpc10_decoder_state *st);

/* encoder */
int prepro_(real *speech, integer *length, struct lpc10_encoder_state *st);
int hp100_(real *speech, integer *start, integer *end, struct lpc10_encoder_state *st);
int analys_(real *speech, integer *voice, integer *pitch, real *rms, real *rc,
            struct lpc10_encoder_state *st);
int preemp_(real *inbuf, real *pebuf, integer *nsamp, real *coef, real *z__);
int onset_(real *pebuf, integer *osbuf, integer *osptr, integer *oslen, integer *sbufl,
           integer *sbufh, integer *lframe, struct lpc10_encoder_state *st);
int placev_(integer *osbuf, integer *osptr, integer *oslen, integer *obound, integer *vwin,
            integer *af, integer *lframe, integer *minwin, integer *maxwin, integer *dvwinl,
            integer *dvwinh);
int lpfilt_(real *inbuf, real *lpbuf, integer *len, integer *nsamp);
int ivfilt_(real *lpbuf, real *ivbuf, integer *len, integer *nsamp, real *ivrc);
int tbdm_(real *speech, integer *lpita, integer *tau, integer *ltau, real *amdf, integer *minptr,
          integer *maxptr, integer *mintau);
int difmag_(real *speech, integer *lpita, integer *tau, integer *ltau, integer *maxlag, real *amdf,
            integer *minptr, integer *maxptr);
int voicin_(integer *vwin, real *inbuf, real *lpbuf, integer *buflim, integer *half, real *minamd,
            real *maxamd, integer *mintau, real *ivrc, integer *obound, integer *voibuf,
            integer *af, struct lpc10_encoder_state *st);
int vparms_(integer *vwin, real *inbuf, real *lpbuf, integer *buflim, integer *half, real *dither,
            integer *mintau, integer *zc, integer *lbe, integer *fbe, real *qs, real *rc1,
            real *ar_b__, real *ar_f__);
int dyptrk_(real *amdf, integer *ltau, integer *minptr, integer *voice, integer *pitch,
            integer *midx, struct lpc10_encoder_state *st);
int placea_(integer *ipitch, integer *voibuf, integer *obound, integer *af, integer *vwin,
            integer *awin, integer *ewin, integer *lframe, integer *maxwin);
int dcbias_(integer *len, real *speech, real *sigout);
int energy_(integer *len, real *speech, real *rms);
int mload_(integer *order, integer *awins, integer *awinf, real *speech, real *phi, real *psi);
int invert_(integer *order, real *phi, real *psi, real *rc);
int rcchk_(integer *order, real *rc1f, real *rc2f);
int encode_(integer *voice, integer *pitch, real *rms, real *rc, integer *ipitch, integer *irms,
            integer *irc);
int chanwr_0_(int n__, integer *order, integer *ipitv, integer *irms, integer *irc,
              integer *ibits, struct lpc10_encoder_state *st);
int chanwr_(integer *order, integer *ipitv, integer *irms, integer *irc, integer *ibits,
            struct lpc10_encoder_state *st);
int chanrd_(integer *order, integer *ipitv, integer *irms, integer *irc, integer *ibits);

/* decoder */
int decode_(integer *ipitv, integer *irms, integer *irc, integer *voice, integer *pitch, real *rms,
            real *rc, struct lpc10_decoder_state *st);
int ham84_(integer *input, integer *output, integer *errcnt);
integer median_(integer *d1, integer *d2, integer *d3);
int synths_(integer *voice, integer *pitch, real *rms, real *rc, real *speech, integer *k,
            struct lpc10_decoder_state *st);
int pitsyn_(integer *order, integer *voice, integer *pitch, real *rms, real *rc, integer *lframe,
            integer *ivuv, integer *ipiti, real *rmsi, real *rci, integer *nout, real *ratio,
            struct lpc10_decoder_state *st);
int irc2pc_(real *rc, real *pc, integer *order, real *gprime, real *g2pass);
int bsynz_(real *coef, integer *ip, integer *iv, real *sout, real *rms, real *ratio, real *g2pass,
           struct lpc10_decoder_state *st);
integer random_(struct lpc10_decoder_state *st);
int deemp_(real *x, integer *n, struct lpc10_decoder_state *st);

/* f2clib.c: the f2c run-time helpers the units use */
integer pow_ii(integer *ap, integer *bp);
real r_sign(real *a, real *b);
integer i_nint(real *x);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_PORT_LPC10_H */
