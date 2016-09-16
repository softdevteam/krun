"""
Iterations runner for Python VMs.
Derived from iterations_runner.php.

Executes a benchmark many times within a single process.

In Kalibera terms, this script represents one executions level run.
"""

import cffi, sys, imp, os


ffi = cffi.FFI()

ffi.cdef("""
    void libkruntime_init();
    void libkruntime_done();
    double clock_gettime_monotonic();
    uint64_t read_core_cycles();
    uint64_t read_aperf();
    uint64_t read_mperf();
""")
libkruntime = ffi.dlopen("libkruntime.so")

libkruntime_init = libkruntime.libkruntime_init
libkruntime_done = libkruntime.libkruntime_done
clock_gettime_monotonic = libkruntime.clock_gettime_monotonic
read_core_cycles = libkruntime.read_core_cycles
read_aperf = libkruntime.read_aperf
read_mperf = libkruntime.read_mperf

# main
if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.stderr.write("usage: iterations_runner.py <benchmark> "
                         "<# of iterations> <benchmark param> <debug flag> "
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

    libkruntime_init()

    # Pre-allocate result lists
    wallclock_times = [0] * iters
    cycle_counts = [0] * iters
    aperf_counts = [0] * iters
    mperf_counts = [0] * iters

    # Main loop
    for i in xrange(iters):
        if instrument:
            start_snap = pypyjit.get_stats_snapshot()
        if debug:
            sys.stderr.write(
                "[iterations_runner.py] iteration %d/%d\n" % (i + 1, iters))

        # Start timed section
        mperf_start = read_mperf()
        aperf_start = read_aperf()
        cycles_start = read_core_cycles()
        wallclock_start = clock_gettime_monotonic()

        bench_func(param)

        wallclock_stop = clock_gettime_monotonic()
        cycles_stop = read_core_cycles()
        aperf_stop = read_aperf()
        mperf_stop = read_mperf()
        # End timed section

        # Sanity checks
        if wallclock_start > wallclock_stop:
            sys.stderr.write("wallclock start is greater than stop\n")
            sys.stderr.write("start=%s, stop=%s\n" %
                             (wallclock_start, wallclock_stop))
            sys.exit(1)

        if cycles_start > cycles_stop:
            sys.stderr.write("cycles start is greater than stop\n")
            sys.stderr.write("start=%s, stop=%s\n" %
                             (cycles_start, cycles_stop))
            sys.exit(1)

        if aperf_start > aperf_stop:
            sys.stderr.write("aperf start is greater than stop\n")
            sys.stderr.write("start=%s, stop=%s\n" %
                             (aperf_start, aperf_stop))
            sys.exit(1)

        if mperf_start > mperf_stop:
            sys.stderr.write("mperf start is greater than stop\n")
            sys.stderr.write("start=%s, stop=%s\n" %
                             (mperf_start, mperf_stop))
            sys.exit(1)

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

        wallclock_times[i] = wallclock_stop - wallclock_start
        cycle_counts[i] = cycles_stop - cycles_start
        aperf_counts[i] = aperf_stop - aperf_start
        mperf_counts[i] = mperf_stop - mperf_start

    libkruntime_done()

    wallclock_times_ls = ", ".join(str(x) for x in wallclock_times)
    cycle_counts_ls = ", ".join(str(x) for x in cycle_counts)
    aperf_counts_ls = ", ".join(str(x) for x in aperf_counts)
    mperf_counts_ls = ", ".join(str(x) for x in mperf_counts)

    sys.stdout.write("[[%s], [%s], [%s], [%s]]\n" % \
                     (wallclock_times_ls, cycle_counts_ls, aperf_counts_ls,
                      mperf_counts_ls))
