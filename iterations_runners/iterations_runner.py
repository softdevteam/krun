"""
Iterations runner for Python VMs.
Derived from iterations_runner.php.

Executes a benchmark many times within a single process.

In Kalibera terms, this script represents one executions level run.
"""

import cffi, sys, imp, os

ffi = cffi.FFI()
ffi.cdef("double clock_gettime_monotonic();")
libkruntime = ffi.dlopen("libkruntime.so")

clock_gettime_monotonic = libkruntime.clock_gettime_monotonic

# main
if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("usage: iterations_runner.py "
        "<benchmark> <# of iterations> <benchmark param> <debug flag> <instrument_flag>\n")
        sys.exit(1)

    benchmark, iters, param, debug, instrument = sys.argv[1:]
    iters, param, debug, instrument = \
        int(iters), int(param), int(debug) == 1, int(instrument) == 1

    assert benchmark.endswith(".py")
    bench_mod_name = os.path.basename(benchmark[:-3])
    bench_mod = imp.load_source(bench_mod_name, benchmark)

    # The benchmark should provide a function called "run_iter" which
    # represents one iterations level run of the benchmark.
    bench_func = bench_mod.run_iter

    # OK, all is well, let's run.

    iter_times = [-1.0] * iters
    for i in xrange(iters):
        if debug:
            sys.stderr.write(
                "[iterations_runner.py] iteration %d/%d\n" % (i + 1, iters))

        start_time = clock_gettime_monotonic()
        bench_func(param)
        stop_time = clock_gettime_monotonic()

        # In instrumentation mode, write a iteration separator to stderr.
        if instrument:
            sys.stderr.write("@@@ END_IN_PROC_ITER: %d\n" % i)
            sys.stderr.flush()

        iter_times[i] = stop_time - start_time

    sys.stdout.write("[")
    for i in xrange(iters):
        print("%f" % iter_times[i])
        if i < iters - 1:
            sys.stdout.write(", ")
    sys.stdout.write("]\n")
