#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <string.h>
#include <unistd.h>

#include "../libkruntime.h"

void test_tsr_u64(void);
void test_tsr_double(void);
void test_tsr_double_prec_ok(void);
void test_tsr_double_prec_bad(void);
void test_tsr_u64_double_ratio(void);
void test_clock_gettime_monotonic(void);

void usage();

void
usage()
{
    printf("usages:\n");
    printf("  test tsr_u64\n");
    printf("  test tsr_double\n");
    printf("  test tsr_double_prec_ok\n");
    printf("  test tsr_double_prec_bad\n");
    printf("  test tsr_u64_double_ratio\n");
    printf("  test clock_gettime_monotonic\n");

    exit(EXIT_FAILURE);
}

int
main(int argc, char **argv)
{
    char *mode;

    if (argc != 2) {
        usage();
    }

    mode = argv[1];

    if (strcmp(mode, "tsr_u64") == 0) {
        test_tsr_u64();
    } else if (strcmp(mode, "tsr_double") == 0) {
        test_tsr_double();
    } else if (strcmp(mode, "tsr_double_prec_ok") == 0) {
        test_tsr_double_prec_ok();
    } else if (strcmp(mode, "tsr_double_prec_bad") == 0) {
        test_tsr_double_prec_bad();
    } else if (strcmp(mode, "tsr_u64_double_ratio") == 0) {
        test_tsr_u64_double_ratio();
    } else if (strcmp(mode, "clock_gettime_monotonic") == 0) {
        test_clock_gettime_monotonic();
    } else {
        usage();
    }

    return (EXIT_SUCCESS);
}

void
test_tsr_u64(void) {
    uint64_t t1, t2, delta;

    t1 = read_ts_reg_start();
    t2 = read_ts_reg_stop();
    delta = t2 - t1;

    printf("tsr_u64_start= %" PRIu64 "\n", t1);
    printf("tsr_u64_stop = %" PRIu64 "\n", t2);
    printf("tsr_u64_delta= %" PRIu64 "\n", delta);
}

void
test_tsr_double(void)
{
    double t1, t2, delta;

    t1 = read_ts_reg_start_double();
    t2 = read_ts_reg_stop_double();
    delta = t2 - t1;

    printf("tsr_double_start= %f\n", t1);
    printf("tsr_double_stop = %f\n", t2);
    printf("tsr_double_delta= %f\n", delta);
}

void
test_tsr_double_prec_ok(void)
{
    (void) u64_to_double(666);
    printf("OK\n");
}

void
test_tsr_double_prec_bad(void)
{
    (void) u64_to_double(((u_int64_t) 1 << 62) - 1);
}

void
test_tsr_u64_double_ratio(void)
{
    u_int64_t i_time1, i_time2, i_delta;
    double d_time1, d_time2, d_delta, ratio;

    i_time1 = read_ts_reg_start();
    i_time2 = read_ts_reg_stop();

    d_time1 = read_ts_reg_start_double();
    d_time2 = read_ts_reg_stop_double();

    i_delta = i_time2 - i_time1;
    d_delta = d_time2 - d_time1;
    ratio = i_delta / d_delta;

    printf("tsr_u64_double_ratio=%f\n", ratio);
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
