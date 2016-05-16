/*
 * Dummy benchmark that checks the CPU affinity mask for a *pinned* benchmark.
 *
 * The mask should contain all CPUs apart from the boot processor (enforced by
 * a cset shield).
 *
 * This code is Linux specific.
 */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>
#include <errno.h>
#include <sched.h>
#include <unistd.h>


void
run_iter(int param)
{
    pid_t pid;
    cpu_set_t mask;
    size_t mask_sz;
    int ret, i;
    long n_cpus;

    (void) param;
    pid = getpid();
    n_cpus = sysconf(_SC_NPROCESSORS_ONLN);
    mask_sz = sizeof(mask);

    ret = sched_getaffinity(pid, mask_sz, &mask);
    if (ret != 0) {
        perror("sched_getaffinity");
        exit(EXIT_FAILURE);
    }

    if (CPU_COUNT(&mask) != n_cpus - 1) {
        fprintf(stderr, "Wrong number of CPUs in affinity mask\n"
            "got %d, expect %ld\n", CPU_COUNT(&mask), n_cpus - 1);
        exit(EXIT_FAILURE);
    }

    if (CPU_ISSET(0, &mask)) {
        fprintf(stderr, "CPU 0 should not be in affinity mask\n");
        exit(EXIT_FAILURE);
    }

    for (i = 1; i < n_cpus; i++) {
        if (!CPU_ISSET(i, &mask)) {
            fprintf(stderr, "CPU %d not in affinity mask\n", i);
            exit(EXIT_FAILURE);
        }
    }
}
