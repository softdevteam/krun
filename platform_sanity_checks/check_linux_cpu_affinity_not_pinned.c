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
 * Dummy benchmark that checks the CPU affinity mask for a *unpinned* benchmark.
 *
 * The mask should contain all CPUs.
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

    if (CPU_COUNT(&mask) != n_cpus) {
        fprintf(stderr, "Wrong number of CPUs in affinity mask\n"
            "got %d, expect %ld\n", CPU_COUNT(&mask), n_cpus - 1);
        exit(EXIT_FAILURE);
    }

    for (i = 0; i < n_cpus; i++) {
        if (!CPU_ISSET(i, &mask)) {
            fprintf(stderr, "CPU %d not in affinity mask\n", i);
            exit(EXIT_FAILURE);
        }
    }
}
