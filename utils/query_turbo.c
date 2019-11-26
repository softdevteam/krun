/*
 * Small utility to determine if turbo boost is enabled on the *current* core.
 *
 * Use taskset to choose which core.
 */

#define _GNU_SOURCE

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>

/* Thermal/power management CPUID leaf */
#define CPUID_THERM_POWER   0x6

/* Fields of CPUID_THERM_POWER */
#define CPUID_THERM_POWER_TURBO 1 << 1


int
main(void)
{
    uint32_t    eax;
    int         enabled;

    asm volatile(
        "mov %1, %%eax\n\t"
        "cpuid\n\t"
        : "=a" (eax)                // out
        : "i"(CPUID_THERM_POWER)    // in
        :"ebx", "ecx", "edx");      // clobber

    enabled = (eax & CPUID_THERM_POWER_TURBO) != 0;
    printf("%d\n", enabled);

    return (EXIT_SUCCESS);
}
