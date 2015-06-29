"""
Iterations runner for Python VMs.
Derived from iterations_runner.php.

Executes a benchmark many times within a single process.

In Kalibera terms, this script represents one executions level run.
"""

import cffi, sys, imp

ANSI_MAGENTA = '\033[95m'
ANSI_RESET = '\033[0m'

ffi = cffi.FFI()
ffi.cdef("double clock_gettime_monotonic();")
libkruntime = ffi.dlopen("libkruntime.so")

clock_gettime_monotonic = libkruntime.clock_gettime_monotonic

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

        start_time = clock_gettime_monotonic()
        bench_func(param)
        stop_time = clock_gettime_monotonic()

        sys.stdout.write("%f, " % (stop_time - start_time))
        sys.stdout.flush()

    sys.stdout.write("]\n")
