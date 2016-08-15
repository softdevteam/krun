"""
Iterations runner for Python VMs.
Derived from iterations_runner.php.

Executes a benchmark many times within a single process.

In Kalibera terms, this script represents one executions level run.
"""

import cffi, sys, imp, os

ffi = cffi.FFI()
ffi.cdef("""
    double clock_gettime_monotonic();
    uint64_t read_ts_reg();
""")
libkruntime = ffi.dlopen("libkruntime.so")

clock_gettime_monotonic = libkruntime.clock_gettime_monotonic
read_ts_reg = libkruntime.read_ts_reg

# main
if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("usage: iterations_runner.py "
              "<benchmark> <# of iterations> <benchmark param> <debug flag> "
              "<instrument flag>\n")
        sys.exit(1)

    benchmark, iters, param, debug, instrument = sys.argv[1:]
    iters, param, debug, instrument = \
        int(iters), int(param), int(debug) == 1, int(instrument) == 1

    if instrument:
        import pypyjit # instrumentation not supported on CPython yet anyway

    assert benchmark.endswith(".py")
    bench_mod_name = os.path.basename(benchmark[:-3])
    bench_mod = imp.load_source(bench_mod_name, benchmark)

    # The benchmark should provide a function called "run_iter" which
    # represents one iterations level run of the benchmark.
    bench_func = bench_mod.run_iter

    # OK, all is well, let's run.

    iter_times = [0] * iters
    tsr_iter_times = [0] * iters
    for i in xrange(iters):
        if instrument:
            start_snap = pypyjit.get_stats_snapshot()
        if debug:
            sys.stderr.write(
                "[iterations_runner.py] iteration %d/%d\n" % (i + 1, iters))

        start_time = clock_gettime_monotonic()
        tsr_start_time = read_ts_reg()
        bench_func(param)
        tsr_stop_time = read_ts_reg()
        stop_time = clock_gettime_monotonic()

        # In instrumentation mode, write an iteration separator to stderr.
        if instrument:
            sys.stderr.write("@@@ END_IN_PROC_ITER: %d\n" % i)
            end_snap = pypyjit.get_stats_snapshot()
            jit_time = (end_snap.counter_times["TRACING"] -
                        start_snap.counter_times["TRACING"])
            jit_time += (end_snap.counter_times["BACKEND"] -
                        start_snap.counter_times["BACKEND"])
            sys.stderr.write("@@@ JIT_TIME: %s\n" % jit_time)
            sys.stderr.flush()

        iter_times[i] = stop_time - start_time
        tsr_iter_times[i] = tsr_stop_time - tsr_start_time

    iter_times_ls = ", ".join(str(x) for x in iter_times)
    tsc_iter_times_ls = ", ".join(str(x) for x in tsr_iter_times)

    sys.stdout.write("[[%s], [%s]]\n" % (iter_times_ls, tsc_iter_times_ls))
