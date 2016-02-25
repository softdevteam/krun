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
    if len(sys.argv) != 5:
        print("usage: iterations_runner.py "
        "<benchmark> <# of iterations> <benchmark param> <debug flag>\n")
        sys.exit(1)

    benchmark, iters, param, debug = sys.argv[1:]
    iters, param, debug = int(iters), int(param), int(debug)

    assert benchmark.endswith(".py")
    bench_mod_name = os.path.basename(benchmark[:-3])
    bench_mod = imp.load_source(bench_mod_name, benchmark)

    # The benchmark should provide a function called "run_iter" which
    # represents one iterations level run of the benchmark.
    bench_func = bench_mod.run_iter

    # OK, all is well, let's run.

    sys.stdout.write("[") # we are going to print a JSON list
    for i in xrange(iters):
        if debug:
            sys.stderr.write(
                "[iterations_runner.py] iteration %d/%d\n" % (i + 1, iters))

        start_time = clock_gettime_monotonic()
        bench_func(param)
        stop_time = clock_gettime_monotonic()

        sys.stdout.write("%f" % (stop_time - start_time))
        if i < iters - 1:
            sys.stdout.write(", ")

        sys.stdout.flush()

    sys.stdout.write("]\n")
