# The VM needs to be patched to offer up:
#   libkruntime_init()
#   libkruntime_done()
#   read_core_cycles()
#   read_aperf()
#   read_mperf()

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

# main
if __FILE__ == $0
    if ARGV.length != 5
        STDERR.puts "usage: iterations_runner.rb <benchmark> "\
                    "<# of iterations> <benchmark param> <debug flag> "\
                    "<instrument flag>\n"
        Kernel.exit(1)
    end

    benchmark, iters, param, debug = ARGV
    iters = Integer(iters)
    param = Integer(param)
    debug = Integer(debug) > 0

    require("#{benchmark}")

    # Pre-allocate result lists
    wallclock_times = [0] * iters
    cycle_counts = [0] * iters
    aperf_counts = [0] * iters
    mperf_counts = [0] * iters

    libkruntime_init();

    # Main loop
    for iter_num in 0..iters - 1 do
        if debug then
            STDERR.write "[iterations_runner.rb] iteration #{iter_num + 1}/#{iters}\n"
            STDERR.flush  # JRuby doesn't flush on newline.
        end

        # Start timed section
        mperf_start = read_mperf()
        aperf_start = read_aperf()
        cycles_start = read_core_cycles()
        wallclock_start = clock_gettime_monotonic()

        run_iter(param)

        wallclock_stop = clock_gettime_monotonic()
        cycles_stop = read_core_cycles()
        aperf_stop = read_aperf()
        mperf_stop = read_mperf()
        # End timed section

        # Sanity checks
        if wallclock_start > wallclock_stop
            STDERR.puts "wallclock start greater than stop"
            STDERR.puts "start=#{wallclock_start} stop=#{wallclock_stop}"
            exit 1
        end

        if cycles_start > cycles_stop
            STDERR.puts "cycles start greater than stop"
            STDERR.puts "start=#{cycles_start} stop=#{cycles_stop}"
            exit 1
        end

        if aperf_start > aperf_stop
            STDERR.puts "aperf start greater than stop"
            STDERR.puts "start=#{aperf_start} stop=#{aperf_stop}"
            exit 1
        end

        if mperf_start > mperf_stop
            STDERR.puts "mperf start greater than stop"
            STDERR.puts "start=#{mperf_start} stop=#{mperf_stop}"
            exit 1
        end

        # Compute deltas
        wallclock_times[iter_num] = wallclock_stop - wallclock_start
        cycle_counts[iter_num] = cycles_stop - cycles_start
        aperf_counts[iter_num] = aperf_stop - aperf_start
        mperf_counts[iter_num] = mperf_stop - mperf_start
    end

    libkruntime_done();

    # Emit measurements
    STDOUT.write "[["
    for iter_num in 0..iters - 1 do
        STDOUT.write String(wallclock_times[iter_num])
        if iter_num < iters - 1 then
            STDOUT.write ", "
        end
    end
    STDOUT.write "], ["
    for iter_num in 0..iters - 1 do
        STDOUT.write String(cycle_counts[iter_num])
        if iter_num < iters - 1 then
            STDOUT.write ", "
        end
    end
    STDOUT.write "], ["
    for iter_num in 0..iters - 1 do
        STDOUT.write String(aperf_counts[iter_num])
        if iter_num < iters - 1 then
            STDOUT.write ", "
        end
    end
    STDOUT.write "], ["
    for iter_num in 0..iters - 1 do
        STDOUT.write String(mperf_counts[iter_num])
        if iter_num < iters - 1 then
            STDOUT.write ", "
        end
    end
    STDOUT.write "]]\n"
end
