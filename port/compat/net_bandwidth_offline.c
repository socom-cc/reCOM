/* Port compatibility: NetGetBandwidthInfo, the SCE-RT network library's bandwidth metrics
 * (ELF 0x418e80; CHUD::StatusLine's debug status line calls it once a second in a network
 * game). The port has no network layer: no traffic, every metric 0. */
#include <string.h>

void NetGetBandwidthInfo(void *info)
{
    memset(info, 0, 32); /* NetBandwidthInfo: four NetClientMetric {average, max average} */
}
