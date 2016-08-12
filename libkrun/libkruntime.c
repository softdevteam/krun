/*
 * C function to get at the monotonic clock.
 *
 * Code style is KNF with 4 spaces instead of tabs.
 */
#include <time.h>
#include <stdlib.h>
#include <errno.h>
#include <stdio.h>

#if defined(__linux__)
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC_RAW
#else
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC
#endif

u_int64_t read_ts_reg();

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
#include <jni.h>

JNIEXPORT jdouble JNICALL
Java_IterationsRunner_JNI_1clock_1gettime_1monotonic(JNIEnv *e, jclass c) {
    return (jdouble) clock_gettime_monotonic();
}

JNIEXPORT jlong JNICALL
Java_IterationsRunner_JNI_1read_1ts_1reg(JNIEnv *e, jclass c)
{
    return read_ts_reg();
}
#endif

/*
 * Support for reading the TS (timestamp) register.
 *
 * This assumes and x86 CPU.
 *
 * Derived from:
 * $OpenBSD: pctr.h,v 1.5 2014/03/29 18:09:28 guenther Exp $
 */
u_int64_t
read_ts_reg()
{
    u_int32_t hi, lo;

    __asm volatile("rdtsc" : "=d" (hi), "=a" (lo));
    return ((u_int64_t) hi << 32) | (u_int64_t) lo;
}

/*
 * Return TSR as a double.
 *
 * For languages like Lua, where there is suitible integer type
 */
double
read_ts_reg_double()
{
    return (double) read_ts_reg();
}
