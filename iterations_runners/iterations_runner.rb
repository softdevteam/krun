# The VM needs to be patched to offer up:
#   krunt_init()
#   krun_done()
#   krun_measure()
#   krun_get_num_cores()
#   krun_get_core_cycles()
#   krun_get_aperf()
#   krun_get_mperf()

# defined this way so we don't measure the conditional platform check.
if /linux/ =~ RUBY_PLATFORM then
    def clock_gettime_monotonic()
        Process.clock_gettime(Process::CLOCK_MONOTONIC_RAW)
    end
else
    def clock_gettime_monotonic()
        Process.clock_gettime(Process::CLOCK_MONOTONIC)
    end
end

def usage()
    STDERR.puts "usage: iterations_runner.rb <benchmark> "\
        "<# of iterations> <benchmark param>\n           "\
        "<debug flag> [instrumentation dir] [key] [key pexec index]>\n"
    STDERR.puts "Arguments in [] are supplied for instrumentation mode only.\n"
    Kernel.exit(1)
end

# main
if __FILE__ == $0
    if ARGV.length < 4
        usage()
    end

    benchmark, iters, param, debug = ARGV
    iters = Integer(iters)
    param = Integer(param)
    debug = Integer(debug) > 0
    instrument = ARGV.length >= 5

    if instrument and ARGV.length != 7 then
        usage()
    end

    require("#{benchmark}")

    krun_init();
    num_cores = krun_get_num_cores()

    # Pre-allocate result lists
    wallclock_times = [-0.0] * iters
    cycle_counts = []
    aperf_counts = []
    mperf_counts = []
    for core in 0..num_cores - 1 do
        cycle_counts[core] = [-0.0] * iters
        aperf_counts[core] = [-0.0] * iters
        mperf_counts[core] = [-0.0] * iters
    end

    # Main loop
    for iter_num in 0..iters - 1 do
        if debug then
            STDERR.write "[iterations_runner.rb] iteration #{iter_num + 1}/#{iters}\n"
            STDERR.flush
        end

        # Start timed section
        krun_measure(0)
        run_iter(param)
        krun_measure(1)
        # End timed section

        # Compute deltas
        wallclock_times[iter_num] = \
            krun_get_wallclock(1) - \
            krun_get_wallclock(0)

        for core in 0..num_cores - 1 do
            cycle_counts[core][iter_num] = \
                krun_get_core_cycles(1, core) - \
                krun_get_core_cycles(0, core)
            aperf_counts[core][iter_num] = \
                krun_get_aperf(1, core) - \
                krun_get_aperf(0, core)
            mperf_counts[core][iter_num] = \
                krun_get_mperf(1, core) - \
                krun_get_mperf(0, core)
        end
    end

    krun_done();

    # Emit measurements
    require 'json'

    out_hash = {
        'wallclock_times' => wallclock_times,
        'core_cycle_counts' => cycle_counts,
        'aperf_counts' => aperf_counts,
        'mperf_counts' => mperf_counts,
    }

    puts(JSON.generate(out_hash))
end
