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
#endif
