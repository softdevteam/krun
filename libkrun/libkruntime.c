/*
 * C support functions.
 *
 * Code style is KNF with 4 spaces instead of tabs.
 */
#include <time.h>
#include <stdlib.h>
#include <errno.h>
#include <stdio.h>
#include <inttypes.h>

#include "libkruntime.h"

#ifdef WITH_JAVA
#include <jni.h>
#endif

#if defined(__linux__)
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC_RAW
#else
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC
#endif

double
clock_gettime_monotonic()
{
    struct timespec         ts;
    double                  result;

    if ((clock_gettime(ACTUAL_CLOCK_MONOTONIC, &ts)) < 0) {
        perror("clock_gettime");
        exit(1);
    }

    result = ts.tv_sec + ts.tv_nsec * 1e-9;
    return (result);
}

/*
 * JNI Implementation -- Optionally compiled in
 */
#ifdef WITH_JAVA

JNIEXPORT jdouble JNICALL
Java_IterationsRunner_JNI_1clock_1gettime_1monotonic(JNIEnv *e, jclass c) {
    return (jdouble) clock_gettime_monotonic();
}

JNIEXPORT jlong JNICALL
Java_IterationsRunner_JNI_1read_1ts_1reg_1start(JNIEnv *e, jclass c)
{
    return read_ts_reg_start();
}

JNIEXPORT jlong JNICALL
Java_IterationsRunner_JNI_1read_1ts_1reg_1stop(JNIEnv *e, jclass c)
{
    return read_ts_reg_stop();
}
#endif

/*
 * Support for reading the TS (timestamp) register.
 *
 * These functions assume an x86-64 CPU.
 *
 * For more info, see page 16 of:
 *
 * "How to Benchmark Code Execution Times on Intel® IA-32 and IA-64
 * Instruction Set Architectures" by Gabriele Paoloni.
 */

u_int64_t
read_ts_reg_start()
{
    u_int32_t hi, lo;

    __asm volatile (
        "cpuid\n\t"             // Barrier (trashes e[abcd]x)
        "rdtsc\n\t"             // Put TSR in edx:eax, also trashes ecx
        "mov %%edx, %0\n\t"     // Copy out the high 32-bits of TSR
        "mov %%eax, %1\n\t"     // Copy out the low 32-bits of TSR
        // ---
        : "=r" (hi), "=r" (lo)              // outputs
        :                                   // inputs
        : "%rax", "%rbx", "%rcx", "%rdx");  // other clobbers
    return ((u_int64_t) hi << 32) | (u_int64_t) lo;
}

u_int64_t
read_ts_reg_stop()
{
    u_int32_t hi, lo;

    __asm volatile(
        "rdtscp\n\t"                    // Put TSR in edx:eax, also trashes ecx
        "mov %%edx, %0\n\t"             // Copy out the high 32-bits of TSR
        "mov %%eax, %1\n\t"             // Copy out the low 32-bits of TSR
        "cpuid\n\t"                     // Barrier (trashes e[abcd]x)
        // ---
        : "=r" (hi), "=r" (lo)              // outputs
        :                                   // inputs
        : "%rax", "%rbx", "%rcx", "%rdx");  // other clobbers
    return ((u_int64_t) hi << 32) | (u_int64_t) lo;
}

/*
 * For languages like Lua, where there is suitible integer type
 */
double
read_ts_reg_start_double()
{
    return u64_to_double(read_ts_reg_start());
}

double
read_ts_reg_stop_double()
{
    return u64_to_double(read_ts_reg_stop());
}

/*
 * Check for double precision loss.
 *
 * Since some languages cannot represent a u_int64_t, we sometimes have to pass
 * around a double. This is annoying since precision could be silently lost.
 * This function makes loss of precision explicit, stopping the VM.
 *
 * We don't expect to actually see a crash since the TSR is zeroed at reboot,
 * and our benchmarks are not long enough running to generate a large enough
 * TSR value to cause precision loss (you would need a integer that would not
 * fit in a 52-bit unsigned int before precision starts being lost in
 * lower-order bits). Nevertheless, we check it.
 *
 * This routine comes at a small cost (a handful of asm instrs). Note that this
 * cost is a drop in the ocean compared to benchmark workloads.
 */
double
u64_to_double(u_int64_t u64_val)
{
    double d_val = (double) u64_val;
    u_int64_t u64_val2 = (u_int64_t) d_val;

    if (u64_val != u64_val2) {
        fprintf(stderr, "Loss of precision detected!\n");
        fprintf(stderr, "%" PRIu64 " != %" PRIu64 "\n", u64_val, u64_val2);
        exit(EXIT_FAILURE);
    }
    // (otherwise all is well)
    return d_val;
}
