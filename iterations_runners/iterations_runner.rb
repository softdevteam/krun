class AssertionError < RuntimeError
end

# defined this way so we don't measure the conditional platform check.
if RUBY_PLATFORM == "java" then
    # "java" means JRuby.
    def clock_gettime_monotonic()
        # JRuby does not (yet) provide access to the (raw) monotonic clock, and
        # adding support is non-trivial (not as simple as adding the C
        # constant).  For now we patch JRuby/Truffle to expose our libkruntime
        # function.
        Truffle::Primitive.clock_gettime_monotonic()
    end
elsif /linux/ =~ RUBY_PLATFORM then
    def clock_gettime_monotonic()
        Process.clock_gettime(Process::CLOCK_MONOTONIC_RAW)
    end
else
    def clock_gettime_monotonic()
        Process.clock_gettime(Process::CLOCK_MONOTONIC)
    end
end

def assert(cond)
    if not cond
        raise AssertionError
    end
end

# main
if __FILE__ == $0
    if ARGV.length != 5
        puts "usage: iterations_runner.rb <benchmark> <# of iterations> "\
             "<benchmark param> <debug flag> <instrument flag>\n"
        Kernel.exit(1)
    end

    benchmark, iters, param, debug = ARGV
    iters = Integer(iters)
    param = Integer(param)
    debug = Integer(debug) > 0

    assert benchmark.end_with?(".rb")
    require("#{benchmark}")

    iter_times = [-1.0] * iters

    for iter_num in 0..iters - 1 do
        if debug then
            STDERR.write "[iterations_runner.rb] iteration #{iter_num + 1}/#{iters}\n"
            STDERR.flush  # JRuby doesn't flush on newline.
        end

        start_time = clock_gettime_monotonic()
        run_iter(param)
        stop_time = clock_gettime_monotonic()

        iter_times[iter_num] = stop_time - start_time
    end

    STDOUT.write "["
    for iter_num in 0..iters - 1 do
        STDOUT.write String(iter_times[iter_num])
        if iter_num < iters - 1 then
            STDOUT.write ", "
        end
    end
    STDOUT.write "]\n"
end
