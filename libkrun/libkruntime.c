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

/*
 * C support functions for timing.
 *
 * Note that this library contains explicit calls to exit() upon error
 * conditions.
 *
 * This file assumes you are using an x86 system.
 *
 * Code style is KNF with 4 spaces instead of tabs.
 */
#include <time.h>
#include <stdlib.h>
#include <errno.h>
#include <stdio.h>
#include <inttypes.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdbool.h>

#include "libkruntime.h"

#ifdef WITH_JAVA
#include <jni.h>
#endif

#if defined(__linux__)
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC_RAW
#else
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC
#endif

#if defined(__linux__) && !defined(NO_MSRS)
// pick up our Krun syscall numbers
#include <sys/krun-syscall.h>
#endif

/*
 * Structure containing the readings.
 */
struct krun_data {
    double wallclock;
    /* Arrays, one value per core, allocated in krun_init() */
    uint64_t *core_cycles;
    uint64_t *aperf;
    uint64_t *mperf;
};

/* Start and stop measurements */
static struct krun_data krun_mdata[2];

/* Number of per-core performance counter measurements */
static int krun_num_cores = 0;

// Private prototypes
#ifdef __linux__
static void     krun_mdata_bounds_check(int mdata_idx);
#ifndef NO_MSRS
static int      krun_get_fixed_pctr1_width(void);
static void     krun_core_bounds_check(int core);
#endif // NO_MSRS
#endif // __linux__
void            krun_check_mdata(void);

/* Helper functions */
void *
krun_xcalloc(size_t nmemb, size_t size)
{
    void *p;

    p = calloc(nmemb, size);
    if (p == NULL) {
        perror("calloc");
        exit(EXIT_FAILURE);
    }
    return p;
}

#if defined(__linux__) && !defined(NO_MSRS)
static void
krun_core_bounds_check(int core)
{
    if ((core < 0) || (core >= krun_num_cores)) {
        fprintf(stderr, "%s: core out of range\n", __func__);
        exit(EXIT_FAILURE);
    }
}
#endif // defined(__linux__) && !defined(NO_MSRS)

static void
krun_mdata_bounds_check(int mdata_idx)
{
    if ((mdata_idx != 0) && (mdata_idx != 1)) {
        fprintf(stderr, "%s: krun_mdata index out of range\n", __func__);
        exit(EXIT_FAILURE);
    }
}

#if defined(__linux__) && !defined(NO_MSRS)
/*
 * Fixed-function counters vary in size across machines.
 * (configured in initialisation).
 */
static uint64_t krun_pctr_val_mask = 0;

#elif defined(__linux__) && defined(NO_MSRS)
#elif defined(__OpenBSD__)
// We do not yet support performance counters on OpenBSD
#else
#error "Unsupported platform"
#endif // __linux__ && !NO_MSRS

double
krun_clock_gettime_monotonic()
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

int
krun_get_num_cores(void)
{
    return krun_num_cores;
}

/*
 * JNI wrappers -- Optionally compiled in
 */
#ifdef WITH_JAVA
JNIEXPORT void JNICALL
Java_IterationsRunner_JNI_1krun_1init(JNIEnv *e, jclass c) {
    krun_init();
}

JNIEXPORT void JNICALL
Java_IterationsRunner_JNI_1krun_1done(JNIEnv *e, jclass c) {
    krun_done();
}

JNIEXPORT void JNICALL
Java_IterationsRunner_JNI_1krun_1measure(JNIEnv *e, jclass c, jint mdata_idx) {
    krun_measure(mdata_idx);
}

JNIEXPORT jdouble JNICALL
Java_IterationsRunner_JNI_1krun_1get_1wallclock(JNIEnv *e, jclass c,
        jint mdata_idx) {
    return krun_get_wallclock(mdata_idx);
}

JNIEXPORT jdouble JNICALL
Java_IterationsRunner_JNI_1krun_1clock_1gettime_1monotonic(JNIEnv *e, jclass c) {
    return krun_clock_gettime_monotonic();
}

JNIEXPORT jlong JNICALL
Java_IterationsRunner_JNI_1krun_1get_1core_1cycles(JNIEnv *e, jclass c,
        int mdata_idx, jint core)
{
    return krun_get_core_cycles(mdata_idx, core);
}

JNIEXPORT jlong JNICALL
Java_IterationsRunner_JNI_1krun_1get_1aperf(JNIEnv *e, jclass c, jint mdata_idx,
        jint core)
{
    return krun_get_aperf(mdata_idx, core);
}

JNIEXPORT jlong JNICALL
Java_IterationsRunner_JNI_1krun_1get_1mperf(JNIEnv *e, jclass c, jint mdata_idx,
        jint core)
{
    return krun_get_mperf(mdata_idx, core);
}

JNIEXPORT jint JNICALL
Java_IterationsRunner_JNI_1krun_1get_1num_1cores(JNIEnv *e, jclass c)
{
    return krun_get_num_cores();
}
#endif

#if defined(__linux__) && !defined(NO_MSRS)
static int
/*
 * Fetches the width of the fixed-function performance counters so we can
 * correctly mask the values we read from the core-cycle counters.
 */
krun_get_fixed_pctr1_width()
{
    uint32_t eax, edx;
    int fixed_ctr_width, arch_ctr_vers, num_fixed_ctrs;

    asm volatile(
        "mov $0xa, %%eax\n\t"       // pctr leaf
        "cpuid\n\t"
        : "=a" (eax), "=d" (edx)    // out
        :                           // in
        : "ebx", "ecx");            // clobber

    /* eax
     *   0-4:  number of fixed-func counters
     *   5-12: width of counters
     */
    num_fixed_ctrs = edx & 0x1f;
    fixed_ctr_width = (edx & 0x1fe0) >> 5;

    /* eax
     *   0-7:  architectural counter version
     *   8-31: reserved
     */
    arch_ctr_vers = eax & 0xff;

    // fixed function perf ctrs appeared on arch counter version 2
    if (arch_ctr_vers < 2) {
        printf("arch pctr version >=2 is required! got %d\n", arch_ctr_vers);
        exit(EXIT_FAILURE);
    }

    /*
     * We are interested in the existence of IA32_FIXED_CTR1, (i.e. the second
     * fixed counter)
     */
    if (num_fixed_ctrs < 2) {
        fprintf(stderr, "too few fixed-function counters: %d\n",
            num_fixed_ctrs);
        exit(EXIT_FAILURE);
    }

    return fixed_ctr_width;
}
#elif defined(__linux__) && defined(NO_MSRS)
#elif defined(__OpenBSD__)
// We do not yet support performance counters on OpenBSD
#else
#error "Unsupported platform"
#endif // linux && !NO_MSRS

void
krun_init(void)
{
#if defined(__linux__) && !defined(NO_MSRS)
    int i, err;

    /* See how wide the counter values are and make an appropriate mask */
    krun_pctr_val_mask = ((uint64_t) 1 << krun_get_fixed_pctr1_width()) - 1;

    /* Initialise (both) measurements structs */
    krun_num_cores = sysconf(_SC_NPROCESSORS_ONLN);
    for (i = 0; i < 2; i++) {
        krun_mdata[i].core_cycles = krun_xcalloc(krun_num_cores, sizeof(uint64_t));
        krun_mdata[i].aperf = krun_xcalloc(krun_num_cores, sizeof(uint64_t));
        krun_mdata[i].mperf = krun_xcalloc(krun_num_cores, sizeof(uint64_t));
    }

    /* Configure and reset CPU_CLK_UNHALTED.CORE on all CPUs */
    err = syscall(SYSCALL_KRUN_CONFIGURE, krun_num_cores);
    if (err) {
        fprintf(stderr, "krun_configure() syscall failed\n");
        exit(EXIT_FAILURE);
    }

    /* Reset all MSRs of interest */
    syscall(SYSCALL_KRUN_RESET_MSRS, krun_num_cores);

#elif defined(__linux__) && defined(NO_MSRS)
#elif defined(__OpenBSD__)
    // We do not yet support performance counters on OpenBSD
#else
#   error "Unsupported platform"
#endif  // __linux__ && !NO_MSRS
}

void
krun_done(void)
{
#if defined(__linux__) && !defined(NO_MSRS)
    int i;

    /* Free per-core arrays */
    for (i = 0; i < 2; i++) {
        free(krun_mdata[i].core_cycles);
        free(krun_mdata[i].aperf);
        free(krun_mdata[i].mperf);
    }
#elif defined(__linux__) && defined(NO_MSRS)
#elif defined(__OpenBSD__)
    // We do not yet support performance counters on OpenBSD
#else
#error "Unsupported platform"
#endif  // __linux__ && !NO_MSRS
}

/*
 * Since some languages cannot represent a uint64_t, we sometimes have to pass
 * around a double. Since the integer part of a double is only 52-bit, loss of
 * precision is theoretically possible should a benchmark run long enough. This
 * function makes loss of precision explicit via an exit(3).
 */
double
krun_u64_to_double(uint64_t u64_val)
{
    double d_val = (double) u64_val;
    uint64_t u64_val2 = (uint64_t) d_val;

    if (u64_val != u64_val2) {
        fprintf(stderr, "Loss of precision detected!\n");
        fprintf(stderr, "%" PRIu64 " != %" PRIu64 "\n", u64_val, u64_val2);
        exit(EXIT_FAILURE);
    }
    // (otherwise all is well)
    return d_val;
}

/*
 * Load up the results struct.
 */
void
krun_measure(int mdata_idx)
{
    struct krun_data *data = &(krun_mdata[mdata_idx]);
    krun_mdata_bounds_check(mdata_idx);

#if defined(__linux__) && !defined(NO_MSRS)
    int err;

    /*
     * Read the MSRs as fast as possible and in the right order.
     *
     * Wallclock time is innermost, as it is the most important reading (with
     * the least latency also).
     *
     * Although APERF/MPERF are separate measurements, they are used together
     * later to make a ratio, so they are taken in the same order before/after
     * benchmarking. Reading APERF, MPERF and the core cycle counter happens inside a
     * system call.
     */
    if (mdata_idx == 0) {
        // taking pre-in-process-iteration readings
        err = syscall(SYSCALL_KRUN_READ_MSRS, krun_num_cores, false, data->aperf,
            data->mperf, data->core_cycles);
        data->wallclock = krun_clock_gettime_monotonic();
    } else {
        // taking post-in-process-iteration readings
        data->wallclock = krun_clock_gettime_monotonic();
        err = syscall(SYSCALL_KRUN_READ_MSRS, krun_num_cores, true, data->aperf,
            data->mperf, data->core_cycles);
    }

    if (err) {
        fprintf(stderr, "krun_read_msrs() syscall failed\n");
        exit(EXIT_FAILURE);
    }
#elif defined(__linux__) && defined(NO_MSRS)
    data->wallclock = krun_clock_gettime_monotonic();
#elif defined(__OpenBSD__)
    data->wallclock = krun_clock_gettime_monotonic();
#else
#error "Unsupported platform"
#endif
    if (mdata_idx == 1) {
        krun_check_mdata();
    }
}

/*
 * Check all of the measurements for issues.
 */
void
krun_check_mdata(void)
{
    int core;

    if (krun_mdata[0].wallclock > krun_mdata[1].wallclock) {
        fprintf(stderr, "wallclock error: start=%f, stop=%f\n",
                krun_mdata[0].wallclock, krun_mdata[1].wallclock);
        exit(EXIT_FAILURE);
    }

    for (core = 0; core < krun_num_cores; core++) {
        if (krun_mdata[0].core_cycles[core] >
                krun_mdata[1].core_cycles[core]) {
            fprintf(stderr, "core_cycles error: "
                    "start=%" PRIu64 ", stop=%" PRIu64 "\n",
                    krun_mdata[0].core_cycles[core],
                    krun_mdata[1].core_cycles[core]);
            exit(EXIT_FAILURE);
        }

        if (krun_mdata[0].aperf[core] >
                krun_mdata[1].aperf[core]) {
            fprintf(stderr, "aperf error: "
                    "start=%" PRIu64 ", stop=%" PRIu64 "\n",
                    krun_mdata[0].aperf[core], krun_mdata[1].aperf[core]);
            exit(EXIT_FAILURE);
        }

        if (krun_mdata[0].mperf[core] > krun_mdata[1].mperf[core]) {
            fprintf(stderr, "mperf error: "
                    "start=%" PRIu64 ", stop=%" PRIu64 "\n",
                    krun_mdata[0].mperf[core], krun_mdata[1].mperf[core]);
            exit(EXIT_FAILURE);
        }
    }
}

double
krun_get_wallclock(int mdata_idx)
{
    krun_mdata_bounds_check(mdata_idx);
    return krun_mdata[mdata_idx].wallclock;
}

uint64_t
krun_get_core_cycles(int mdata_idx, int core)
{
#if defined(__linux__) && !defined(NO_MSRS)
    krun_mdata_bounds_check(mdata_idx);
    krun_core_bounds_check(core);
    return krun_mdata[mdata_idx].core_cycles[core] & krun_pctr_val_mask;
#else
    fprintf(stderr, "%s: libkruntime was built without MSR support\n", __func__);
    exit(EXIT_FAILURE);
#endif // defined(__linux__) && !defined(NO_MSRS)
}

uint64_t
krun_get_aperf(int mdata_idx, int core)
{
#if defined(__linux__) && !defined(NO_MSRS)
    krun_mdata_bounds_check(mdata_idx);
    krun_core_bounds_check(core);
    return krun_mdata[mdata_idx].aperf[core];
#else
    fprintf(stderr, "%s: libkruntime was built without MSR support\n", __func__);
    exit(EXIT_FAILURE);
#endif // defined(__linux__) && !defined(NO_MSRS)
}

uint64_t
krun_get_mperf(int mdata_idx, int core)
{
#if defined(__linux__) && !defined(NO_MSRS)
    krun_mdata_bounds_check(mdata_idx);
    krun_core_bounds_check(core);
    return krun_mdata[mdata_idx].mperf[core];
#else
    fprintf(stderr, "%s: libkruntime was built without MSR support\n", __func__);
    exit(EXIT_FAILURE);
#endif // defined(__linux__) && !defined(NO_MSRS)
}

/*
 * For languages like Lua, where there is no suitible integer type
 */
double
krun_get_core_cycles_double(int mdata_idx, int core)
{
    return krun_u64_to_double(krun_get_core_cycles(mdata_idx, core));
}

double
krun_get_aperf_double(int mdata_idx, int core)
{
    return krun_u64_to_double(krun_get_aperf(mdata_idx, core));
}

double
krun_get_mperf_double(int mdata_idx, int core)
{
    return krun_u64_to_double(krun_get_mperf(mdata_idx, core));
}
