/*
 * Copyright (c) 2017 King's College London
 * created by the Software Development Team <http://soft-dev.org/>
 *
 * The Universal Permissive License (UPL), Version 1.0
 *
 * Subject to the condition set forth below, permission is hereby granted to
 * any person obtaining a copy of this software, associated documentation
 * and/or data (collectively the "Software"), free of charge and under any and
 * all copyright rights in the Software, and any and all patent rights owned or
 * freely licensable by each licensor hereunder covering either (i) the
 * unmodified Software as contributed to or provided by such licensor, or (ii)
 * the Larger Works (as defined below), to deal in both
 *
 * (a) the Software, and
 * (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
 * one is included with the Software (each a "Larger Work" to which the
 * Software is contributed by such licensors),
 *
 * without restriction, including without limitation the rights to copy, create
 * derivative works of, display, perform, and distribute the Software and make,
 * use, sell, offer for sale, import, export, have made, and have sold the
 * Software and the Larger Work(s), and to sublicense the foregoing rights on
 * either these or other terms.
 *
 * This license is subject to the following condition: The above copyright
 * notice and either this complete permission notice or at a minimum a
 * reference to the UPL must be included in all copies or substantial portions
 * of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
 * IN THE SOFTWARE.
 */

// NOTE: JS VM will need to be patched to allow access to:
//
//   krun_init()
//   krun_done()
//   krun_measure()
//   krun_get_num_cores()
//   krun_get_{core_cycles,aperf,mperf}_double()
//   krun_get_wallclock()

function emitPerCoreResults(name, num_cores, ary) {
    write('"' + name + '": [')
    for (core = 0; core < num_cores; core++) {
        write("[")
        for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
            write(ary[core][BM_i]);

            if (BM_i < BM_n_iters - 1) {
                write(", ")
            }
        }
        write("]")
        if (core < num_cores - 1) {
            write(", ")
        }
    }
    write("]")
}

function usage() {
    throw "\nusage: iterations_runner.js <benchmark> <# of iterations> " +
          "<benchmark param>\n       <debug flag> [instrumentation dir] [key] " +
          "[key pexec index]\n\nArguments in [] are for" +
          "instrumentation mode only.\n";
}

if (this.arguments.length < 4) {
    usage();
}

var BM_entry_point = this.arguments[0];
var BM_n_iters = parseInt(this.arguments[1]);
var BM_param = parseInt(this.arguments[2]);
var BM_debug = parseInt(this.arguments[3]) > 0;
var BM_instrument = this.arguments.length >= 5;

if (BM_instrument && (this.arguments.length != 7)) {
    usage();
}

load(BM_entry_point);

krun_init();
var BM_num_cores = krun_get_num_cores();

// Pre-allocate and fill arrays.
// We use typed arrays to encourage type stability.
var BM_wallclock_times = new Float64Array(BM_n_iters);
BM_wallclock_times.fill(-0.0);

var BM_cycle_counts = new Array(BM_num_cores);
var BM_aperf_counts = new Array(BM_num_cores);
var BM_mperf_counts = new Array(BM_num_cores);

for (BM_core = 0; BM_core < BM_num_cores; BM_core++) {
    BM_cycle_counts[BM_core] = new Float64Array(BM_n_iters);
    BM_aperf_counts[BM_core] = new Float64Array(BM_n_iters);
    BM_mperf_counts[BM_core] = new Float64Array(BM_n_iters);

    BM_cycle_counts[BM_core].fill(-0.0);
    BM_aperf_counts[BM_core].fill(-0.0);
    BM_mperf_counts[BM_core].fill(-0.0);
}

// Main loop
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    if (BM_debug) {
        printErr("[iterations_runner.js] iteration " + (BM_i + 1) + "/" + BM_n_iters);
    }

    // Start timed section
    krun_measure(0);
    run_iter(BM_param);
    krun_measure(1);
    // End timed section

    // Compute deltas
    BM_wallclock_times[BM_i] = krun_get_wallclock(1) - krun_get_wallclock(0);

    for (BM_core = 0; BM_core < BM_num_cores; BM_core++) {
        BM_cycle_counts[BM_core][BM_i] =
            krun_get_core_cycles_double(1, BM_core) -
            krun_get_core_cycles_double(0, BM_core);
        BM_aperf_counts[BM_core][BM_i] =
            krun_get_aperf_double(1, BM_core) -
            krun_get_aperf_double(0, BM_core);
        BM_mperf_counts[BM_core][BM_i] =
            krun_get_mperf_double(1, BM_core) -
            krun_get_mperf_double(0, BM_core);
    }
}

krun_done();

// Emit measurements
write("{")

write('"wallclock_times": [')
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    write(BM_wallclock_times[BM_i]);

    if (BM_i < BM_n_iters - 1) {
        write(", ")
    }
}
write("], ")

emitPerCoreResults("core_cycle_counts", BM_num_cores, BM_cycle_counts)
write(", ")
emitPerCoreResults("aperf_counts", BM_num_cores, BM_aperf_counts)
write(", ")
emitPerCoreResults("mperf_counts", BM_num_cores, BM_mperf_counts)

write("}")
