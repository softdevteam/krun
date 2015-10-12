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

#define BENCH_FUNC_NAME "run_iter"

/* from libkruntime */
double clock_gettime_monotonic();

int
convert_str_to_int(char *s)
{
    long r = strtol(s, NULL, 10);

    if (errno != 0) {
        perror("strtoll");
        exit(EXIT_FAILURE);
    }

    if (r == 0) {
        /* Zero used as an error case.
         * Pretty bad since zero is also a valid result.
         * Anyway, the user should never pass a zero so
         * we are OK in this case.
         */
        errx(EXIT_FAILURE, "strtoll failed");
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
    void     *krun_dl_handle = 0;
    int     (*krun_bench_func)(int); /* func ptr to benchmark entry */
    double    start_time = -1, stop_time = -1;

    if (argc != 4) {
        printf("usage: iterations_runner_c "
            "<benchmark> <# of iterations> <benchmark param>\n");
        exit(EXIT_FAILURE);
    }

    krun_benchmark = argv[1];
    krun_total_iters = convert_str_to_int(argv[2]);
    krun_param = convert_str_to_int(argv[3]);

    krun_dl_handle = dlopen(krun_benchmark, RTLD_NOW | RTLD_LOCAL);
    if (krun_dl_handle == NULL) {
        errx(EXIT_FAILURE, dlerror());
        goto clean;
    }

    /* Odd pointer gymnastics are intentional. See Linux dlopen manual */
    *(void **) (&krun_bench_func) = dlsym(krun_dl_handle, BENCH_FUNC_NAME);
    if (krun_bench_func == NULL) {
        errx(EXIT_FAILURE, dlerror());
        goto clean;
    }

    /* Building a JSON list */
    fprintf(stdout, "[");
    fflush(stdout);

    for (krun_iter_num = 0;
        krun_iter_num < krun_total_iters; krun_iter_num++) {

        fprintf(stderr, "[iterations_runner.c] iteration %d/%d\n",
            krun_iter_num + 1, krun_total_iters);

        /* timed section */
        start_time = clock_gettime_monotonic();
        (void) (*krun_bench_func)(krun_param);
        stop_time = clock_gettime_monotonic();

        fprintf(stdout, "%f", (stop_time - start_time));
        if (krun_iter_num < krun_total_iters - 1) {
            fprintf(stdout, ", ");
        }

        fflush(stdout);
    }

    fprintf(stdout, "]\n");

clean:
    if (krun_dl_handle != NULL) {
        dlclose(krun_dl_handle);
    }

    return (EXIT_SUCCESS);
}
