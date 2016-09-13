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

int
main(int argc, char **argv)
{
    char     *krun_benchmark = 0;
    int       krun_total_iters = 0, krun_param = 0, krun_iter_num = 0;
    int       krun_debug = 0;
    void     *krun_dl_handle = 0;
    int     (*krun_bench_func)(int); /* func ptr to benchmark entry */
    double    krun_wallclock_start = -1, krun_wallclock_stop = -1;
    double   *krun_wallclock_times = NULL;
    u_int64_t krun_cycles_start = 0, krun_cycles_stop = 0;
    u_int64_t *krun_cycle_counts = NULL;

    if (argc != 6) {
        printf("usage: iterations_runner_c "
            "<benchmark> <# of iterations> <benchmark param> <debug flag> "
            "<instrument flag>\n");
        exit(EXIT_FAILURE);
    }

    krun_benchmark = argv[1];
    krun_total_iters = convert_str_to_int(argv[2]);
    krun_param = convert_str_to_int(argv[3]);
    krun_debug = convert_str_to_int(argv[4]);

    libkruntime_init();

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

    krun_wallclock_times = calloc(krun_total_iters, sizeof(double));
    if (krun_wallclock_times == NULL) {
        errx(EXIT_FAILURE, "%s", strerror(errno));
        goto clean;
    }

    krun_cycle_counts = calloc(krun_total_iters, sizeof(u_int64_t));
    if (krun_cycle_counts == NULL) {
        errx(EXIT_FAILURE, "%s", strerror(errno));
        goto clean;
    }

    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {
        krun_wallclock_times[krun_iter_num] = 0;
        krun_cycle_counts[krun_iter_num] = 0;
    }

    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {

        if (krun_debug > 0) {
            fprintf(stderr, "[iterations_runner.c] iteration %d/%d\n",
                krun_iter_num + 1, krun_total_iters);
        }

        /* timed section */
        krun_cycles_start = read_core_cycles();
        krun_wallclock_start = clock_gettime_monotonic();
        (void) (*krun_bench_func)(krun_param);
        krun_wallclock_stop = clock_gettime_monotonic();
        krun_cycles_stop = read_core_cycles();

        if (krun_cycles_start > krun_cycles_stop) {
            fprintf(stderr, "cycle count start greater than stop\n");
            fprintf(stderr, "start=%" PRIu64 ", stop=%" PRIu64 "\n",
                krun_cycles_start, krun_cycles_stop);
            exit(EXIT_FAILURE);
        }

        if (krun_wallclock_start > krun_wallclock_stop) {
            fprintf(stderr, "wallclock time start greater than stop\n");
            fprintf(stderr, "start=%f, stop=%f\n",
                krun_wallclock_start, krun_wallclock_stop);
            exit(EXIT_FAILURE);
        }

        krun_wallclock_times[krun_iter_num] =
            krun_wallclock_stop - krun_wallclock_start;
        krun_cycle_counts[krun_iter_num] =
            krun_cycles_stop - krun_cycles_start;
    }

    /* Emit results */
    fprintf(stdout, "[[");
    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {
        fprintf(stdout, "%f", krun_wallclock_times[krun_iter_num]);

        if (krun_iter_num < krun_total_iters - 1) {
            fprintf(stdout, ", ");
        }
    }
    fprintf(stdout, "], \n[");
    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {
        fprintf(stdout, "%" PRIu64, krun_cycle_counts[krun_iter_num]);

        if (krun_iter_num < krun_total_iters - 1) {
            fprintf(stdout, ", ");
        }
    }
    fprintf(stdout, "]]\n");

clean:
    free(krun_wallclock_times);

    if (krun_dl_handle != NULL) {
        dlclose(krun_dl_handle);
    }

    libkruntime_done();

    return (EXIT_SUCCESS);
}
