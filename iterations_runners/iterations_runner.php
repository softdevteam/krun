<?php
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

/*
 * Note, you will need to patch the VM so as to allow access to:
 *  krun_init();
 *  krun_done();
 *  krun_measure();
 *  krun_get_num_cores();
 *  krun_get_wallclock();
 *  krun_get_{core_cycles,aperf,mperf}_double();
 */

function usage() {
    fwrite(STDERR, "usage: iterations_runner.php <benchmark> <# of iterations> " .
        "<benchmark param>\n           <debug flag> [instrumentation dir] " .
        "[key] [key pexec index]>\n\n");
    fwrite(STDERR, "Arguments in [] are for instrumentation mode only.\n");
    exit(1);
}

if ($argc < 5) {
    usage();
}

$BM_benchmark = $argv[1];
$BM_iters = $argv[2];
$BM_param = (int) $argv[3];
$BM_debug = ((int) $argv[4]) > 0;
$BM_instrument = $argc >= 6;

if ($BM_instrument && ($argc != 8)) {
    usage();
}

if (!file_exists($BM_benchmark)) {
    throw new RuntimeException("Can't find $BM_benchmark");
}

include($BM_benchmark);

// Find benchmark entry point
if (!function_exists("run_iter")) {
    throw new RuntimeException("Benchmark is missing a 'run_iter' function");
}

krun_init();
$BM_num_cores = krun_get_num_cores();

// Pre-allocate results arrays
$BM_wallclock_times = array_fill(0, $BM_iters, -0.0);
$BM_cycle_counts = array_fill(0, $BM_num_cores, array());
$BM_aperf_counts = array_fill(0, $BM_num_cores, array());
$BM_mperf_counts = array_fill(0, $BM_num_cores, array());
for ($BM_core = 0; $BM_core < $BM_num_cores; $BM_core++) {
    $BM_cycle_counts[$BM_core] = array_fill(0, $BM_iters, -0.0);
    $BM_aperf_counts[$BM_core] = array_fill(0, $BM_iters, -0.0);
    $BM_mperf_counts[$BM_core] = array_fill(0, $BM_iters, -0.0);
}

// Main loop
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    if ($BM_debug) {
        fprintf(STDERR, "[iterations_runner.php] iteration %d/%d\n", $BM_i + 1, $BM_iters);
    }

    // Start timed section
    krun_measure(0);
    run_iter($BM_param);
    krun_measure(1);
    // End timed section

    // Compute deltas
    $BM_wallclock_times[$BM_i] = krun_get_wallclock(1) - krun_get_wallclock(0);

    for ($BM_core = 0; $BM_core < $BM_num_cores; $BM_core++) {
        $BM_cycle_counts[$BM_core][$BM_i] =
            krun_get_core_cycles_double(1, $BM_core) -
            krun_get_core_cycles_double(0, $BM_core);
        $BM_aperf_counts[$BM_core][$BM_i] =
            krun_get_aperf_double(1, $BM_core) -
            krun_get_aperf_double(0, $BM_core);
        $BM_mperf_counts[$BM_core][$BM_i] =
            krun_get_mperf_double(1, $BM_core) -
            krun_get_mperf_double(0, $BM_core);
    }
}

krun_done();

$BM_output = array(
    "wallclock_times" => $BM_wallclock_times,
    "core_cycle_counts" => $BM_cycle_counts,
    "aperf_counts" => $BM_aperf_counts,
    "mperf_counts" => $BM_mperf_counts
);

echo json_encode($BM_output);

?>
