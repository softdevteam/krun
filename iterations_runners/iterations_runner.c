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
 * Iterations runner for C benchmarks.
 *
 * Code style here is KNF, but with 4 spaces instead of tabs.
 */

/* To correctly expose asprintf() on Linux */
#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <stdlib.h>
#include <errno.h>
#include <dlfcn.h>
#include <err.h>
#include <string.h>
#include <inttypes.h>

#include "../libkrun/libkruntime.h"

#define BENCH_FUNC_NAME "run_iter"

// Private protos
int convert_str_to_int(char *s);
void emit_per_core_data(char *name, int num_cores, int num_iters, uint64_t **data);

void
emit_per_core_data(char *name, int num_cores, int num_iters, uint64_t **data)
{
    int core, iter_num;

    fprintf(stdout, "\"%s\": [", name);
    for (core = 0; core < num_cores; core++) {
        fprintf(stdout, "[");

        for (iter_num = 0; iter_num < num_iters; iter_num++) {
            fprintf(stdout, "%" PRIu64, data[core][iter_num]);

            if (iter_num < num_iters - 1) {
                fprintf(stdout, ", ");
            }
        }

        fprintf(stdout, "]");
        if (core < num_cores - 1) {
            fprintf(stdout, ", ");
        }
    }
    fprintf(stdout, "]");
}

int
convert_str_to_int(char *s)
{
    char *endptr;
    long r;

    errno = 0; /* errno not set to 0 on success */
    r = strtol(s, &endptr, 10);

    if ((errno != 0) || (*endptr != 0)) {
        perror("strtoll");
        exit(EXIT_FAILURE);
    }

    if ((r > INT_MAX) || (r < INT_MIN)) {
        fprintf(stderr, "Number would be truncated! %ld\n", r);
        exit (EXIT_FAILURE);
    }

    return ((int) r);
}

void
usage() {
    printf("usage: iterations_runner_c <benchmark> <# of iterations> "
           "<benchmark param>\n             <debug flag> [instrumentation dir] "
           "[key] [key pexec index]\n\n");
    printf("Arguments in [] are for instrumentation mode only.\n");
    exit(EXIT_FAILURE);
}

int
main(int argc, char **argv)
{
    char     *krun_benchmark = 0;
    int       krun_total_iters = 0, krun_param = 0, krun_iter_num = 0;
    int       krun_debug = 0, krun_num_cores = 0, krun_core, krun_instrument = 0;
    void     *krun_dl_handle = 0;
    int     (*krun_bench_func)(int); /* func ptr to benchmark entry */
    double   *krun_wallclock_times = NULL;
    uint64_t **krun_cycle_counts = NULL, **krun_aperf_counts = NULL;
    uint64_t **krun_mperf_counts = NULL;

    if (argc < 5) {
        usage();
    }

    krun_benchmark = argv[1];
    krun_total_iters = convert_str_to_int(argv[2]);
    krun_param = convert_str_to_int(argv[3]);
    krun_debug = convert_str_to_int(argv[4]);
    krun_instrument = argc >= 6;

    if (krun_instrument && (argc != 8)) {
        usage();
    }

    krun_init();
    krun_num_cores = krun_get_num_cores();

    krun_dl_handle = dlopen(krun_benchmark, RTLD_NOW | RTLD_LOCAL);
    if (krun_dl_handle == NULL) {
        errx(EXIT_FAILURE, "%s", dlerror());
        goto clean;
    }

    /* Odd pointer gymnastics are intentional. See Linux dlopen manual */
    *(void **) (&krun_bench_func) = dlsym(krun_dl_handle, BENCH_FUNC_NAME);
    if (krun_bench_func == NULL) {
        errx(EXIT_FAILURE, "%s", dlerror());
        goto clean;
    }

    /* Allocate arrays */
    krun_wallclock_times = krun_xcalloc(krun_total_iters, sizeof(double));
    krun_cycle_counts = krun_xcalloc(krun_num_cores, sizeof(uint64_t *));
    krun_aperf_counts = krun_xcalloc(krun_num_cores, sizeof(uint64_t *));
    krun_mperf_counts = krun_xcalloc(krun_num_cores, sizeof(uint64_t *));
    for (krun_core = 0; krun_core < krun_num_cores; krun_core++) {
        krun_cycle_counts[krun_core] =
            krun_xcalloc(krun_total_iters, sizeof(uint64_t));
        krun_aperf_counts[krun_core] =
            krun_xcalloc(krun_total_iters, sizeof(uint64_t));
        krun_mperf_counts[krun_core] =
            krun_xcalloc(krun_total_iters, sizeof(uint64_t));
    }

    /* Set default values */
    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
            krun_iter_num++) {
        for (krun_core = 0; krun_core < krun_num_cores; krun_core++) {
            krun_cycle_counts[krun_core][krun_iter_num] = 0;
            krun_aperf_counts[krun_core][krun_iter_num] = 0;
            krun_mperf_counts[krun_core][krun_iter_num] = 0;
        }
        krun_wallclock_times[krun_iter_num] = 0;
    }

    /* Main loop */
    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {

        if (krun_debug > 0) {
            fprintf(stderr, "[iterations_runner.c] iteration %d/%d\n",
                krun_iter_num + 1, krun_total_iters);
        }

        /* Start timed section */
        krun_measure(0);
        (void) (*krun_bench_func)(krun_param);
        krun_measure(1);
        /* End timed section */

        /* Extract and store wallclock data from libkruntime */
        krun_wallclock_times[krun_iter_num] =
            krun_get_wallclock(1) - krun_get_wallclock(0);

        /* Same for per-core measurements */
        for (krun_core = 0; krun_core < krun_num_cores; krun_core++ ) {
            krun_cycle_counts[krun_core][krun_iter_num] =
                krun_get_core_cycles(1, krun_core) -
                krun_get_core_cycles(0, krun_core);
            krun_aperf_counts[krun_core][krun_iter_num] =
                krun_get_aperf(1, krun_core) - krun_get_aperf(0, krun_core);
            krun_mperf_counts[krun_core][krun_iter_num] =
                krun_get_mperf(1, krun_core) - krun_get_mperf(0, krun_core);
        }
    }

    /* Emit results */
    fprintf(stdout, "{ \"wallclock_times\": [");
    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {
        fprintf(stdout, "%f", krun_wallclock_times[krun_iter_num]);

        if (krun_iter_num < krun_total_iters - 1) {
            fprintf(stdout, ", ");
        }
    }
    fprintf(stdout, "], ");

    emit_per_core_data("core_cycle_counts", krun_num_cores, krun_total_iters,
            krun_cycle_counts);
    fprintf(stdout, ", ");

    emit_per_core_data("aperf_counts", krun_num_cores, krun_total_iters,
            krun_aperf_counts);
    fprintf(stdout, ", ");

    emit_per_core_data("mperf_counts", krun_num_cores, krun_total_iters,
            krun_mperf_counts);

    fprintf(stdout, "}\n");

clean:
    /* Free up allocations */
    for (krun_core = 0; krun_core < krun_num_cores; krun_core++) {
        free(krun_cycle_counts[krun_core]);
        free(krun_aperf_counts[krun_core]);
        free(krun_mperf_counts[krun_core]);
    }
    free(krun_wallclock_times);
    free(krun_cycle_counts);
    free(krun_aperf_counts);
    free(krun_mperf_counts);

    if (krun_dl_handle != NULL) {
        dlclose(krun_dl_handle);
    }

    krun_done();

    return (EXIT_SUCCESS);
}
