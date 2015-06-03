"""
Iterations runner for Python VMs.
Derived from iterations_runner.php.

Executes a benchmark many times within a single process.

In Kalibera terms, this script represents one executions level run.
"""

import cffi, sys, imp
import gc

ANSI_MAGENTA = '\033[95m'
ANSI_RESET = '\033[0m'

CDEFS = """
double clock_gettime_monotonic();
"""

CSRC = """
#include <time.h>
#include <stdlib.h>
#include <math.h>

#if defined(__linux__)
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC_RAW
#else
#define ACTUAL_CLOCK_MONOTONIC    CLOCK_MONOTONIC
#endif

double
clock_gettime_monotonic()
{
    struct timespec         ts;
    double                  result;

    if ((clock_gettime(ACTUAL_CLOCK_MONOTONIC, &ts)) < 0) {
        perror("clock_gettime");
        exit(1);
    }

    result = ts.tv_sec + ts.tv_nsec * pow(10, -9);
    return (result);
}
"""

LINK_LIBS = []
if sys.platform.startswith("linux"):
    LINK_LIBS += ["rt"]

ffi = cffi.FFI()
ffi.cdef(CDEFS)
our_lib = ffi.verify(CSRC, libraries=LINK_LIBS)

clock_gettime_monotonic = our_lib.clock_gettime_monotonic

class BenchTimer(object):

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        self.start_time = clock_gettime_monotonic()

    def stop(self):
        self.stop_time = clock_gettime_monotonic()
        if self.start_time is None:
            raise RuntimeError("timer was not started")

    def get(self):
        if self.stop_time is None:
            raise RuntimeError("timer was not stopped")
        return self.stop_time - self.start_time

# main
if __name__ == "__main__":

    if len(sys.argv) != 4:
        print("usage: iterations_runner.php "
        "<benchmark> <# of iterations> <benchmark param>\n")
        sys.exit(1)

    benchmark, iters, param = sys.argv[1:]
    iters, param = int(iters), int(param)

    assert benchmark.endswith(".py")
    bench_mod_name = benchmark[:-3].replace("/", ".") # doesn't really matter
    bench_mod = imp.load_source(bench_mod_name, benchmark)

    # The benchmark should provide a function called "run_iter" which
    # represents one iterations level run of the benchmark.
    bench_func = bench_mod.run_iter

    # OK, all is well, let's run.

    sys.stdout.write("[") # we are going to print a Python eval-able list.
    for i in xrange(iters):
        sys.stderr.write("    %sIteration %3d/%3d%s\n" %
                         (ANSI_MAGENTA, i + 1, iters, ANSI_RESET))

        timer = BenchTimer()
        gc.collect()
        timer.start()
        bench_func(param)
        timer.stop()

        sys.stdout.write("%f, " % timer.get())
        sys.stdout.flush()

    sys.stdout.write("]\n")
