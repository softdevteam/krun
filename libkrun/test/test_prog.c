#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <string.h>
#include <unistd.h>

#include "../libkruntime.h"

void test_cycles_u64(void);
void test_cycles_double(void);
void test_cycles_double_prec_ok(void);
void test_cycles_double_prec_bad(void);
void test_cycles_u64_double_ratio(void);
void test_clock_gettime_monotonic(void);
void test_msr_time(void);

void usage();

void
usage()
{
    printf("usages:\n");
    printf("  test cycles_u64\n");
    printf("  test cycles_double\n");
    printf("  test cycles_double_prec_ok\n");
    printf("  test cycles_double_prec_bad\n");
    printf("  test cycles_u64_double_ratio\n");
    printf("  test clock_gettime_monotonic\n");
    printf("  test msr_time\n");
}

int
main(int argc, char **argv)
{
    char *mode;
    int rv = EXIT_SUCCESS;

    if (argc != 2) {
        usage();
        return (EXIT_FAILURE);
    }

    mode = argv[1];

    if (strcmp(mode, "cycles_u64") == 0) {
        libkruntime_init();
        test_cycles_u64();
        libkruntime_done();
    } else if (strcmp(mode, "cycles_double") == 0) {
        libkruntime_init();
        test_cycles_double();
        libkruntime_done();
    } else if (strcmp(mode, "cycles_double_prec_ok") == 0) {
        libkruntime_init();
        test_cycles_double_prec_ok();
        libkruntime_done();
    } else if (strcmp(mode, "cycles_double_prec_bad") == 0) {
        libkruntime_init();
        test_cycles_double_prec_bad();
        libkruntime_done();
    } else if (strcmp(mode, "cycles_u64_double_ratio") == 0) {
        libkruntime_init();
        test_cycles_u64_double_ratio();
        libkruntime_done();
    } else if (strcmp(mode, "msr_time") == 0) {
        libkruntime_init();
        test_msr_time();
        libkruntime_done();
    } else if (strcmp(mode, "clock_gettime_monotonic") == 0) {
        test_clock_gettime_monotonic();  // doesn't need init/done
    } else {
        usage();
        rv = EXIT_FAILURE;
    }

    return (rv);
}

void
test_cycles_u64(void) {
    uint64_t t1, t2, delta;

    t1 = read_core_cycles();
    t2 = read_core_cycles();
    delta = t2 - t1;

    printf("cycles_u64_start= %" PRIu64 "\n", t1);
    printf("cycles_u64_stop = %" PRIu64 "\n", t2);
    printf("cycles_u64_delta= %" PRIu64 "\n", delta);
}

void
test_cycles_double(void)
{
    double t1, t2, delta;

    t1 = read_core_cycles_double();
    t2 = read_core_cycles_double();
    delta = t2 - t1;

    printf("cycles_double_start= %f\n", t1);
    printf("cycles_double_stop = %f\n", t2);
    printf("cycles_double_delta= %f\n", delta);
}

void
test_cycles_double_prec_ok(void)
{
    (void) u64_to_double(666);
    printf("OK\n");
}

void
test_cycles_double_prec_bad(void)
{
    (void) u64_to_double(((u_int64_t) 1 << 62) - 1);
}

void
test_cycles_u64_double_ratio(void)
{
    u_int64_t i_time1, i_time2, i_delta;
    double d_time1, d_time2, d_delta, ratio;

    i_time1 = read_core_cycles();
    i_time2 = read_core_cycles();

    d_time1 = read_core_cycles_double();
    d_time2 = read_core_cycles_double();

    i_delta = i_time2 - i_time1;
    d_delta = d_time2 - d_time1;
    ratio = i_delta / d_delta;

    printf("cycles_u64_double_ratio=%f\n", ratio);
}

void
test_clock_gettime_monotonic()
{
    double t1, t2, delta;

    t1 = clock_gettime_monotonic();
    sleep(1);
    t2 = clock_gettime_monotonic();
    delta = t2 - t1;

    printf("monotonic_start= %f\n", t1);
    printf("monotonic_stop = %f\n", t2);
    printf("monotonic_delta= %f\n", delta);
}

void
test_msr_time(void)
{
    double t1, t2, t3, t4, delta1, delta2;
    uint64_t c1, c2;

    // time doing "nothing"
    t1 = clock_gettime_monotonic();
    t2 = clock_gettime_monotonic();
    delta1 = t2 - t1;

    // time two msr reads
    t3 = clock_gettime_monotonic();
    c1 = read_core_cycles();
    c2 = read_core_cycles();
    t4 = clock_gettime_monotonic();
    delta2 = t4 - t3;

    printf("monotonic_start_nothing= %f\n", t1);
    printf("monotonic_stop_nothing = %f\n", t2);
    printf("monotonic_delta_nothing= %f\n", delta1);

    printf("monotonic_start_msrs   = %f\n", t3);
    printf("monotonic_stop_msrs    = %f\n", t4);
    printf("cycles_u64_start       = %" PRIu64 "\n", c1);
    printf("cycles_u64_stop        = %" PRIu64 "\n", c2);
    printf("monotonic_delta_msrs   = %f\n", delta2);
}
