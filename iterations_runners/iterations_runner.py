"""
Iterations runner for Python VMs.
Derived from iterations_runner.php.

Executes a benchmark many times within a single process.

In Kalibera terms, this script represents one executions level run.
"""

import cffi, sys, imp, os


ffi = cffi.FFI()

ffi.cdef("""
    void krun_init(void);
    void krun_done(void);
    double krun_measure(int);
    uint64_t krun_get_num_cores(void);
    double krun_get_wallclock(int);
    uint64_t krun_get_core_cycles(int, int);
    uint64_t krun_get_aperf(int, int);
    uint64_t krun_get_mperf(int, int);
""")
libkruntime = ffi.dlopen("libkruntime.so")

krun_init = libkruntime.krun_init
krun_done = libkruntime.krun_done
krun_measure = libkruntime.krun_measure
krun_get_num_cores = libkruntime.krun_get_num_cores
krun_get_wallclock = libkruntime.krun_get_wallclock
krun_get_core_cycles = libkruntime.krun_get_core_cycles
krun_get_aperf = libkruntime.krun_get_aperf
krun_get_mperf = libkruntime.krun_get_mperf

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

    krun_init()
    num_cores = krun_get_num_cores()

    # Pre-allocate result lists
    wallclock_times = [0] * iters
    cycle_counts = [None] * num_cores
    aperf_counts = [None] * num_cores
    mperf_counts = [None] * num_cores
    for core in xrange(num_cores):
        cycle_counts[core] = [0] * iters
        aperf_counts[core] = [0] * iters
        mperf_counts[core] = [0] * iters

    # Main loop
    for i in xrange(iters):
        if instrument:
            start_snap = pypyjit.get_stats_snapshot()
        if debug:
            sys.stderr.write(
                "[iterations_runner.py] iteration %d/%d\n" % (i + 1, iters))

        # Start timed section
        krun_measure(0)
        bench_func(param)
        krun_measure(1)
        # End timed section

        # Extract/check/store wallclock time
        wallclock_times[i] = krun_get_wallclock(1) - krun_get_wallclock(0)

        # Extract/check/store per-core data
        for core in xrange(num_cores):
            cycle_counts[core][i] = (
                krun_get_core_cycles(1, core) -
                krun_get_core_cycles(0, core))
            aperf_counts[core][i] = (
                krun_get_aperf(1, core) -
                krun_get_aperf(0, core))
            mperf_counts[core][i] = (
                krun_get_mperf(1, core) -
                krun_get_mperf(0, core))

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

    krun_done()

    import json
    js = {
        "wallclock_times": wallclock_times,
        "core_cycle_counts": cycle_counts,
        "aperf_counts": aperf_counts,
        "mperf_counts": mperf_counts
    }

    sys.stdout.write("%s\n" % json.dumps(js))
