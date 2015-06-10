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

class BenchTimer
    def initialize()
        @start_time = nil;
        @end_time = nil;
    end

    def start
        assert @start_time == nil
        @start_time = clock_gettime_monotonic()
    end

    def stop
        @end_time = clock_gettime_monotonic()
        assert @start_time != nil
    end

    def read
        assert @end_time != nil
        @end_time - @start_time
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
    require("./" + benchmark)

    STDOUT.write "["
    iters.times do
        t = BenchTimer.new()
        t.start()
        run_iter(param)
        t.stop()
        STDOUT.write String(t.read()) + ", "
    end
    STDOUT.write "]"
end
