/*
 * C function to get at the monotonic clock.
 */
#include <time.h>
#include <stdlib.h>
#include <math.h>
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

    result = ts.tv_sec + ts.tv_nsec * pow(10, -9);
    return (result);
}
