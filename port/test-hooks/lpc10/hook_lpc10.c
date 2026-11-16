/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. Its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-lpc10, an offline self-test of the LPC-10 codec
 * (port/compat/lpc10/, docs/port/notes/lpc10.md). Wraps scePadRead; SOCOM_HOOK_LPC_AT ticks (1/30 s,
 * default 200) after the main menu came up (the fake pad's menu anchor, port/tools/dev/hook_clock.h) it
 * runs, once, on synthetic 8 kHz input:
 *   segment S  silence                                  SOCOM_LPC_FR frames each (default 30)
 *   segment V  100 Hz pulse train (period 80) through three formant resonators (700, 1220,
 *              2600 Hz), amplitude about 0.3
 *   segment N  white noise (LCG, uniform +-0.3)
 *   segment X  voiced (period 57, 140 Hz) and noise, switching every 8 frames
 * Every frame goes through lpc10_encode (180 samples -> 54 bits) on encoder state A and through
 * the same steps one by one (prepro_, analys_, encode_, chanwr_) on encoder state B, whose bits
 * must equal A's; the parameters of B are traced. The bits go through lpc10_decode (decoder state
 * C) and, for the trace, through chanrd_ + decode_ on decoder state D. Per frame (HOOK: LPC f ...):
 * segment, input RMS, analysis voicing (two half frames) / pitch index and its lag / RMS / RC1..RC3, the 54 bits as
 * 14 hex digits, decoded voicing / pitch / RMS, decoded output RMS. At the end: per-segment
 * summaries, a count of non-finite values, and the whole run repeated on fresh states with the
 * checksums of the bits and of the output compared (HOOK: LPC run1 / run2 / same). The segment
 * layout follows the analysis delay: the analysis parameters of frame f belong to input frame f-2;
 * the decoder adds about one more frame. */
#include "../../compat/lpc10/lpc10.h"
#include <string.h>
#include <stdio.h>

#ifndef SOCOM_HOOK_LPC_AT
#define SOCOM_HOOK_LPC_AT 200
#endif
#ifndef SOCOM_LPC_FR
#define SOCOM_LPC_FR 30
#endif
#define NSEG 4
#define NFRAMES (NSEG * SOCOM_LPC_FR)

void socom_port_trace(const char *fmt, ...);
int __real_scePadRead(int port, int slot, unsigned char *rdata);

static int done;
/* the fake pad's time base (port/compat/libpad.c; hook_clock.h is C++ only) */
extern unsigned int socom_fake_fields(void);
extern int socom_fake_anchor_field(const char *name, unsigned int k);
/* analys_'s lag table (0x43c3f0): the encoder's pitch is an index into it */
static const int tau[60] = { 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40,
    42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80, 84, 88, 92, 96, 100,
    104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 148, 152, 156 };
static int lag(int p) { return p >= 1 && p <= 60 ? tau[p - 1] : 0; }
static unsigned int lcg;
static struct lpc10_encoder_state enc_a, enc_b;
static struct lpc10_decoder_state dec_c, dec_d;

static float noise(void)
{
    lcg = lcg * 1103515245u + 12345u;
    return ((float)((lcg >> 8) & 0xffff) / 32768.f - 1.f) * .3f;
}

/* one two-pole resonator per formant (y = x + a1 y1 - a2 y2), coefficients for 8 kHz */
struct reso { float a1, a2, y1, y2; };
static void reso_init(struct reso *r, float f, float bw)
{
    float rr = expf(-3.14159265f * bw / 8000.f);
    r->a1 = 2.f * rr * cosf(2.f * 3.14159265f * f / 8000.f);
    r->a2 = rr * rr;
    r->y1 = r->y2 = 0.f;
}
static float reso_run(struct reso *r, float x)
{
    float y = x + r->a1 * r->y1 - r->a2 * r->y2;
    r->y2 = r->y1;
    r->y1 = y;
    return y;
}

static struct reso f1, f2, f3;
static int phase;

static float voiced(int period)
{
    float x = (phase++ % period) == 0 ? 1.f : 0.f;
    float y = reso_run(&f1, x);
    y = reso_run(&f2, y);
    y = reso_run(&f3, y);
    return y;
}

static char seg_of(int f)
{
    static const char names[NSEG] = { 'S', 'V', 'N', 'X' };
    return names[f / SOCOM_LPC_FR];
}

/* input frame f (180 samples) */
static void make_frame(int f, float *s, float gain)
{
    int i;
    char g = seg_of(f);
    for (i = 0; i < 180; i++) {
        if (g == 'S') {
            s[i] = 0.f;
        } else if (g == 'V') {
            s[i] = voiced(80) * gain;
        } else if (g == 'N') {
            s[i] = noise();
        } else {
            s[i] = ((f / 8) & 1) ? noise() : voiced(57) * gain;
        }
    }
}

static float frame_rms(const float *s)
{
    int i;
    float e = 0.f;
    for (i = 0; i < 180; i++) {
        e += s[i] * s[i];
    }
    return sqrtf(e / 180.f);
}

static int bad_float(float x)
{
    union { float f; unsigned int u; } v;
    v.f = x;
    return (v.u & 0x7f800000u) == 0x7f800000u || !(x == x) || x > 1e30f || x < -1e30f;
}

static unsigned int crc_add(unsigned int c, unsigned int w)
{
    int k;
    c ^= w;
    for (k = 0; k < 32; k++) {
        c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
    return c;
}

struct seg_sum {
    int frames, voiced_halves, pitch_sum, pitch_n, dvoiced, nonfinite;
    float in_rms, an_rms, out_rms;
};

/* one whole run on fresh states; trace != 0 prints the per-frame lines */
static void run(int trace, unsigned int *crc_bits, unsigned int *crc_out, int *mismatch,
                struct seg_sum *sum)
{
    float in[180], copy[180], out[180];
    integer bits_a[54], bits_b[54];
    integer voice[2], pitch, ipitv, irms, irc[10];
    real rms, rc[10];
    integer dbits[54], dvoice[2], dpitch, dipitv, dirms, dirc[10];
    real drms, drc[10];
    float gain;
    int f, i, len;
    char hex[15];

    init_lpc10_encoder_state(&enc_a);
    init_lpc10_encoder_state(&enc_b);
    init_lpc10_decoder_state(&dec_c);
    init_lpc10_decoder_state(&dec_d);
    lcg = 12345u;
    phase = 0;
    reso_init(&f1, 700.f, 130.f);
    reso_init(&f2, 1220.f, 70.f);
    reso_init(&f3, 2600.f, 160.f);
    /* scale the voiced source to about 0.3 RMS from one probe period */
    {
        float probe = 0.f;
        for (i = 0; i < 800; i++) {
            float y = voiced(80);
            probe += y * y;
        }
        gain = .3f / sqrtf(probe / 800.f);
        phase = 0;
        f1.y1 = f1.y2 = f2.y1 = f2.y2 = f3.y1 = f3.y2 = 0.f;
    }
    *crc_bits = *crc_out = 0xffffffffu;
    *mismatch = 0;
    memset(sum, 0, NSEG * sizeof(*sum));

    for (f = 0; f < NFRAMES; f++) {
        struct seg_sum *ss = &sum[f / SOCOM_LPC_FR];
        float irmsv, orms;
        make_frame(f, in, gain);
        irmsv = frame_rms(in);
        /* A: the public entry */
        memcpy(copy, in, sizeof(in));
        lpc10_encode(copy, bits_a, &enc_a);
        /* B: the same steps one by one, keeping the parameters */
        memcpy(copy, in, sizeof(in));
        {
            static integer c180 = 180, c10 = 10;
            prepro_(copy, &c180, &enc_b);
            analys_(copy, voice, &pitch, &rms, rc, &enc_b);
            encode_(voice, &pitch, &rms, rc, &ipitv, &irms, irc);
            chanwr_(&c10, &ipitv, &irms, irc, bits_b, &enc_b);
        }
        if (memcmp(bits_a, bits_b, sizeof(bits_a)) != 0) {
            ++*mismatch;
        }
        /* C: decode to speech */
        lpc10_decode(bits_a, out, &dec_c);
        orms = frame_rms(out);
        /* D: decoded parameters for the trace */
        {
            static integer c10 = 10;
            memcpy(dbits, bits_a, sizeof(dbits));
            chanrd_(&c10, &dipitv, &dirms, dirc, dbits);
            decode_(&dipitv, &dirms, dirc, dvoice, &dpitch, &drms, drc, &dec_d);
        }
        (void)len;
        for (i = 0; i < 54; i++) {
            *crc_bits = crc_add(*crc_bits, (unsigned int)bits_a[i]);
        }
        for (i = 0; i < 180; i++) {
            union { float x; unsigned int u; } v;
            v.x = out[i];
            *crc_out = crc_add(*crc_out, v.u);
            if (bad_float(out[i])) {
                ss->nonfinite++;
            }
        }
        for (i = 0; i < 10; i++) {
            if (bad_float(rc[i]) || bad_float(drc[i])) {
                ss->nonfinite++;
            }
        }
        if (bad_float(rms) || bad_float(drms)) {
            ss->nonfinite++;
        }
        /* the analysis of frame f describes input frame f - 2: count it there */
        if (f >= 2) {
            struct seg_sum *as = &sum[(f - 2) / SOCOM_LPC_FR];
            as->voiced_halves += voice[0] + voice[1];
            if (voice[0] && voice[1]) {
                as->pitch_sum += lag(pitch);
                as->pitch_n++;
            }
            as->an_rms += rms;
        }
        if (f >= 3) {
            struct seg_sum *ds = &sum[(f - 3) / SOCOM_LPC_FR];
            ds->dvoiced += dvoice[0] + dvoice[1];
            ds->out_rms += orms;
        }
        ss->frames++;
        ss->in_rms += irmsv;
        if (trace) {
            for (i = 0; i < 14; i++) {
                int b = 0, k;
                for (k = 0; k < 4; k++) {
                    int n = i * 4 + k;
                    b = (b << 1) | (n < 54 ? (bits_a[n] & 1) : 0);
                }
                hex[i] = "0123456789abcdef"[b];
            }
            hex[14] = 0;
            socom_port_trace("HOOK: LPC f %3d %c in %.4f | an v %d%d p %3d (lag %3d) rms %7.1f rc %+.3f %+.3f %+.3f "
                             "| bits %s | dec v %d%d p %3d rms %7.1f | out %.4f",
                             f, seg_of(f), (double)irmsv, (int)voice[0], (int)voice[1], (int)pitch, lag(pitch),
                             (double)rms, (double)rc[0], (double)rc[1], (double)rc[2], hex,
                             (int)dvoice[0], (int)dvoice[1], (int)dpitch, (double)drms, (double)orms);
        }
    }
}

static void RunTest(void)
{
    static struct seg_sum s1[NSEG], s2[NSEG];
    unsigned int b1, o1, b2, o2;
    int m1, m2, g;

    socom_port_trace("HOOK: LPC self-test start: %d frames (%d per segment S V N X)", NFRAMES, SOCOM_LPC_FR);
    run(1, &b1, &o1, &m1, s1);
    for (g = 0; g < NSEG; g++) {
        struct seg_sum *s = &s1[g];
        int n = s->frames;
        socom_port_trace("HOOK: LPC seg %c: in rms %.4f | analysis voiced halves %d/%d, mean pitch lag %.1f (%d fully voiced) "
                         "mean rms %.1f | decoded voiced halves %d, out rms %.4f | non-finite %d",
                         "SVNX"[g], (double)(s->in_rms / n), s->voiced_halves, 2 * n,
                         s->pitch_n ? (double)s->pitch_sum / s->pitch_n : 0.0, s->pitch_n,
                         (double)(s->an_rms / n), s->dvoiced, (double)(s->out_rms / n), s->nonfinite);
    }
    run(0, &b2, &o2, &m2, s2);
    socom_port_trace("HOOK: LPC run1 bits crc %08x out crc %08x, A/B bit mismatches %d", b1, o1, m1);
    socom_port_trace("HOOK: LPC run2 bits crc %08x out crc %08x, A/B bit mismatches %d", b2, o2, m2);
    socom_port_trace("HOOK: LPC same %d (bits %d, output %d)", b1 == b2 && o1 == o2, b1 == b2, o1 == o2);
}

int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int menu = port == 0 && !done ? socom_fake_anchor_field("menu", 1) : -1;

    if (menu >= 0 && socom_fake_fields() >= (unsigned int)menu + 2 * SOCOM_HOOK_LPC_AT) {
        done = 1;
        RunTest();
    }
    return __real_scePadRead(port, slot, rdata);
}
