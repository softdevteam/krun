# Copyright (c) 2017 King's College London
# created by the Software Development Team <http://soft-dev.org/>
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or
# data (collectively the "Software"), free of charge and under any and all
# copyright rights in the Software, and any and all patent rights owned or
# freely licensable by each licensor hereunder covering either (i) the
# unmodified Software as contributed to or provided by such licensor, or (ii)
# the Larger Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
# one is included with the Software (each a "Larger Work" to which the Software
# is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright
# notice and either this complete permission notice or at a minimum a reference
# to the UPL must be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
