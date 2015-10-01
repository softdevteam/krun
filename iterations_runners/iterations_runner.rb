if /linux/ =~ RUBY_PLATFORM
    MONOTONIC_CLOCK = Process::CLOCK_MONOTONIC_RAW
else
    MONOTONIC_CLOCK = Process::CLOCK_MONOTONIC
end

def clock_gettime_monotonic
    Process.clock_gettime(MONOTONIC_CLOCK)
end

class AssertionError < RuntimeError
end

def assert(cond)
    if not cond
        raise AssertionError
    end
end

# main
if __FILE__ == $0
    if ARGV.length != 3
        puts "usage: iterations_runner.rb <benchmark> <#iterations> <benchmark_param>\n"
        Kernel.exit(1)
    end

    benchmark, iters, param = ARGV
    iters = Integer(iters)
    param = Integer(param)

    assert benchmark.end_with?(".rb")
    require("#{benchmark}")

    STDOUT.write "["
    for krun_iter_num in 0..iters - 1 do  # inclusive upper bound
        STDERR.write "[iterations_runner.rb] iteration #{krun_iter_num + 1}/#{iters}\n"
	STDERR.flush  # JRuby doesn't flush on newline.

        start_time = clock_gettime_monotonic()
        run_iter(param)
        stop_time = clock_gettime_monotonic()

        intvl = stop_time - start_time
        STDOUT.write String(intvl)
        if krun_iter_num < iters - 1 then
            STDOUT.write ", "
        end
    end
    STDOUT.write "]"
end
