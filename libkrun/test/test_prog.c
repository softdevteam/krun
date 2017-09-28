/*
 * Copyright (c) 2017 King's College London
 * created by the Software Development Team <http://soft-dev.org/>
 *
 * The Universal Permissive License (UPL), Version 1.0
 *
 * Subject to the condition set forth below, permission is hereby granted to
 * any person obtaining a copy of this software, associated documentation
 * and/or data (collectively the "Software"), free of charge and under any and
 * all copyright rights in the Software, and any and all patent rights owned or
 * freely licensable by each licensor hereunder covering either (i) the
 * unmodified Software as contributed to or provided by such licensor, or (ii)
 * the Larger Works (as defined below), to deal in both
 *
 * (a) the Software, and
 * (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
 * one is included with the Software (each a "Larger Work" to which the
 * Software is contributed by such licensors),
 *
 * without restriction, including without limitation the rights to copy, create
 * derivative works of, display, perform, and distribute the Software and make,
 * use, sell, offer for sale, import, export, have made, and have sold the
 * Software and the Larger Work(s), and to sublicense the foregoing rights on
 * either these or other terms.
 *
 * This license is subject to the following condition: The above copyright
 * notice and either this complete permission notice or at a minimum a
 * reference to the UPL must be included in all copies or substantial portions
 * of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
 * IN THE SOFTWARE.
 */

#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <string.h>
#include <unistd.h>

#include "../libkruntime.h"

#define TEST_CORE 0

void test_cycles_u64(void);
void test_cycles_double(void);
void test_cycles_double_prec_ok(void);
void test_cycles_double_prec_bad(void);
void test_cycles_u64_double_ratio(void);
void test_clock_gettime_monotonic(void);
void test_aperf_mperf(void);
void test_aperf(void);
void test_mperf(void);
void test_core_bounds_check(void);
void test_mdata_index_bounds_check(void);
void test_read_everything_all_cores(void);

void usage();

void
usage()
{
    printf("usages:\n");
    printf("  test_prog cycles_u64\n");
    printf("  test_prog cycles_double\n");
    printf("  test_prog cycles_double_prec_ok\n");
    printf("  test_prog cycles_double_prec_bad\n");
    printf("  test_prog cycles_u64_double_ratio\n");
    printf("  test_prog clock_gettime_monotonic\n");
    printf("  test_prog aperf_mperf\n");
    printf("  test_prog aperf\n");
    printf("  test_prog mperf\n");
    printf("  test_prog core_bounds_check\n");
    printf("  test_prog mdata_index_bounds_check\n");
    printf("  test_prog read_everything_all_cores\n");
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
        krun_init();
        test_cycles_u64();
        krun_done();
    } else if (strcmp(mode, "cycles_double") == 0) {
        krun_init();
        test_cycles_double();
        krun_done();
    } else if (strcmp(mode, "cycles_double_prec_ok") == 0) {
        krun_init();
        test_cycles_double_prec_ok();
        krun_done();
    } else if (strcmp(mode, "cycles_double_prec_bad") == 0) {
        krun_init();
        test_cycles_double_prec_bad();
        krun_done();
    } else if (strcmp(mode, "cycles_u64_double_ratio") == 0) {
        krun_init();
        test_cycles_u64_double_ratio();
        krun_done();
    } else if (strcmp(mode, "clock_gettime_monotonic") == 0) {
        test_clock_gettime_monotonic();  // doesn't need init/done
    } else if (strcmp(mode, "aperf_mperf") == 0) {
        krun_init();
        test_aperf_mperf();
        krun_done();
    } else if (strcmp(mode, "aperf") == 0) {
        krun_init();
        test_aperf();
        krun_done();
    } else if (strcmp(mode, "mperf") == 0) {
        krun_init();
        test_mperf();
        krun_done();
    } else if (strcmp(mode, "core_bounds_check") == 0) {
        krun_init();
        test_core_bounds_check();
        krun_done();
    } else if (strcmp(mode, "mdata_index_bounds_check") == 0) {
        krun_init();
        test_mdata_index_bounds_check();
        krun_done();
    } else if (strcmp(mode, "read_everything_all_cores") == 0) {
        krun_init();
        test_read_everything_all_cores();
        krun_done();
    } else {
        usage();
        rv = EXIT_FAILURE;
    }

    return (rv);
}

void
test_cycles_u64(void) {
    uint64_t t1, t2, delta;

    krun_measure(0);
    krun_measure(1);

    t1 = krun_get_core_cycles(0, TEST_CORE);
    t2 = krun_get_core_cycles(1, TEST_CORE);
    delta = t2 - t1;

    printf("cycles_u64_start= %" PRIu64 "\n", t1);
    printf("cycles_u64_stop = %" PRIu64 "\n", t2);
    printf("cycles_u64_delta= %" PRIu64 "\n", delta);
}

void
test_cycles_double(void)
{
    double t1, t2, delta;

    t1 = krun_get_core_cycles(0, TEST_CORE);
    t2 = krun_get_core_cycles(1, TEST_CORE);
    delta = t2 - t1;

    printf("cycles_double_start= %f\n", t1);
    printf("cycles_double_stop = %f\n", t2);
    printf("cycles_double_delta= %f\n", delta);
}

void
test_cycles_double_prec_ok(void)
{
    (void) krun_u64_to_double(666);
    printf("OK\n");
}

void
test_cycles_double_prec_bad(void)
{
    (void) krun_u64_to_double(((u_int64_t) 1 << 62) - 1);
}

void
test_cycles_u64_double_ratio(void)
{
    u_int64_t i_time1, i_time2, i_delta;
    double d_time1, d_time2, d_delta, ratio;

    krun_measure(0);
    krun_measure(1);

    i_time1 = krun_get_core_cycles(0, TEST_CORE);
    i_time2 = krun_get_core_cycles(1, TEST_CORE);

    d_time1 = krun_get_core_cycles_double(0, TEST_CORE);
    d_time2 = krun_get_core_cycles_double(1, TEST_CORE);

    i_delta = i_time2 - i_time1;
    d_delta = d_time2 - d_time1;
    ratio = i_delta / d_delta;

    printf("cycles_u64_double_ratio=%f\n", ratio);
}

void
test_clock_gettime_monotonic()
{
    double t1, t2;

    krun_measure(0);
    sleep(1);
    krun_measure(1);

    t1 = krun_get_wallclock(0);
    t2 = krun_get_wallclock(1);

    printf("monotonic_start= %f\n", t1);
    printf("monotonic_stop = %f\n", t2);
}

void
test_aperf_mperf(void)
{
    uint64_t ap, mp;

    krun_measure(0);

    ap = krun_get_aperf(0, TEST_CORE);
    mp = krun_get_mperf(0, TEST_CORE);

    printf("aperf=%" PRIu64 "\n", ap);
    printf("mperf=%" PRIu64 "\n", mp);
}

void
test_aperf(void)
{
    uint64_t p1, p2;

    krun_measure(0);
    krun_measure(1);

    p1 = krun_get_aperf(0, TEST_CORE);
    p2 = krun_get_aperf(1, TEST_CORE);

    printf("aperf_start=%" PRIu64 "\n", p1);
    printf("aperf_stop= %" PRIu64 "\n", p2);
}

void
test_mperf(void)
{
    uint64_t p1, p2;

    krun_measure(0);
    krun_measure(1);

    p1 = krun_get_mperf(0, TEST_CORE);
    p2 = krun_get_mperf(1, TEST_CORE);

    printf("mperf_start=%" PRIu64 "\n", p1);
    printf("mperf_stop= %" PRIu64 "\n", p2);
}

void
test_core_bounds_check(void)
{
    int num_cores = krun_get_num_cores();

    krun_measure(0);
    (void) krun_get_mperf(0, num_cores); // one above the last core
    /* unreachable as the above crashes */
}

void
test_mdata_index_bounds_check(void)
{
    krun_measure(0);
    (void) krun_get_mperf(2, TEST_CORE); // 2 is not a valid mdata index
    /* unreachable as the above crashes */
}

void
test_read_everything_all_cores(void)
{
    int num_cores = krun_get_num_cores();
    int core, idx;

    krun_measure(0);
    krun_measure(1);

    for (idx = 0; idx < 2; idx++) {
        printf("wallclock_%d=    %f\n", idx, krun_get_wallclock(idx));
        for (core = 0; core < num_cores; core++) {
            printf("core_cycles_%d_%d=%" PRIu64 "\n", idx, core,
                    krun_get_core_cycles(idx, core));
            printf("aperf_%d_%d=      %" PRIu64 "\n", idx, core,
                    krun_get_aperf(idx, core));
            printf("mperf_%d_%d=      %" PRIu64 "\n", idx, core,
                    krun_get_mperf(idx, core));
        }
    }
}
