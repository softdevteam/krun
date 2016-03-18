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

#define BENCH_FUNC_NAME "run_iter"

/* from libkruntime */
double clock_gettime_monotonic();

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
    double    start_time = -1, stop_time = -1;
    double   *krun_iter_times = NULL;

    if (argc != 5) {
        printf("usage: iterations_runner_c "
            "<benchmark> <# of iterations> <benchmark param> <debug flag>\n");
        exit(EXIT_FAILURE);
    }

    krun_benchmark = argv[1];
    krun_total_iters = convert_str_to_int(argv[2]);
    krun_param = convert_str_to_int(argv[3]);
    krun_debug = convert_str_to_int(argv[4]);

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

    krun_iter_times = calloc(krun_total_iters, sizeof(double));
    if (krun_iter_times == NULL) {
        errx(EXIT_FAILURE, "%s", strerror(errno));
        goto clean;
    }

    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {
        krun_iter_times[krun_iter_num] = -1.0;
    }

    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {

        if (krun_debug > 0) {
            fprintf(stderr, "[iterations_runner.c] iteration %d/%d\n",
                krun_iter_num + 1, krun_total_iters);
        }

        /* timed section */
        start_time = clock_gettime_monotonic();
        (void) (*krun_bench_func)(krun_param);
        stop_time = clock_gettime_monotonic();

        krun_iter_times[krun_iter_num] = stop_time - start_time;
    }

    fprintf(stdout, "[");
    for (krun_iter_num = 0; krun_iter_num < krun_total_iters;
        krun_iter_num++) {
        fprintf(stdout, "%f", krun_iter_times[krun_iter_num]);

        if (krun_iter_num < krun_total_iters - 1) {
            fprintf(stdout, ", ");
        }
    }
    fprintf(stdout, "]\n");

clean:
    free(krun_iter_times);

    if (krun_dl_handle != NULL) {
        dlclose(krun_dl_handle);
    }

    return (EXIT_SUCCESS);
}
