<?php

/*
 * Note! You will need to provide an implementation of clock_gettime_monotonic()
 */

/*
 * Executes a benchmark many times within a single process.
 *
 * In Kalibera terms, this script represents one executions level run.
 */

# main
if ($argc != 6) {
    fwrite(STDERR, "usage: iterations_runner.php <benchmark> <# of iterations> " .
           "<benchmark param> <debug flag> <instrument flag>\n");
    exit(1);
}

$BM_benchmark = $argv[1];
$BM_iters = $argv[2];
$BM_param = (int) $argv[3]; // parameter sent to benchmark.
$BM_debug = ((int) $argv[4]) > 0;

if (!file_exists($BM_benchmark)) {
    throw new RuntimeException("Can't find $BM_benchmark");
}

include($BM_benchmark);

/*
 * The benchmark should provide a function called "run_iter" which represents
 * one iterations level run of the benchmark.
 */
if (!function_exists("run_iter")) {
    throw new RuntimeException("Benchmark is missing a 'run_iter' function");
}

// Pre-allocate results arrays
$BM_wallclock_times = array_fill(0, $BM_iters, 0);
$BM_cycle_counts = array_fill(0, $BM_iters, 0);
$BM_aperf_counts = array_fill(0, $BM_iters, 0);
$BM_mperf_counts = array_fill(0, $BM_iters, 0);

libkruntime_init();

// Main loop
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    if ($BM_debug) {
        fprintf(STDERR, "[iterations_runner.php] iteration %d/%d\n", $BM_i + 1, $BM_iters);
    }

    // Start timed section
    $BM_mperf_start = read_mperf_double();
    $BM_aperf_start = read_aperf_double();
    $BM_cycles_start = read_core_cycles_double();
    $BM_wallclock_start = clock_gettime_monotonic();

    run_iter($BM_param);

    $BM_wallclock_stop = clock_gettime_monotonic();
    $BM_cycles_stop = read_core_cycles_double();
    $BM_aperf_stop = read_aperf_double();
    $BM_mperf_stop = read_mperf_double();
    // End timed section

    // Sanity checks
    if ($BM_wallclock_start > $BM_wallclock_stop) {
        fwrite(STDERR, "wallclock start greater than stop\n");
        fwrite(STDERR, "start=${BM_wallclock_start} stop=${BM_wallclock_stop}\n");
        exit(1);
    }

    if ($BM_cycles_start > $BM_cycles_stop) {
        fwrite(STDERR, "cycles start greater than stop\n");
        fwrite(STDERR, "start=${BM_cycles_start} stop=${BM_cycles_stop}\n");
        exit(1);
    }

    if ($BM_aperf_start > $BM_aperf_stop) {
        fwrite(STDERR, "aperf start greater than stop\n");
        fwrite(STDERR, "start=${BM_aperf_start} stop=${BM_aperf_stop}\n");
        exit(1);
    }

    if ($BM_mperf_start > $BM_mperf_stop) {
        fwrite(STDERR, "mperf start greater than stop\n");
        fwrite(STDERR, "start=${BM_mperf_start} stop=${BM_mperf_stop}\n");
        exit(1);
    }

    // Compute deltas
    $BM_wallclock_times[$BM_i] = $BM_wallclock_stop - $BM_wallclock_start;
    $BM_cycle_counts[$BM_i] = $BM_cycles_stop - $BM_cycles_start;
    $BM_aperf_counts[$BM_i] = $BM_aperf_stop - $BM_aperf_start;
    $BM_mperf_counts[$BM_i] = $BM_mperf_stop - $BM_mperf_start;
}

libkruntime_done();

// Emit measurements
echo "[[";
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    echo $BM_wallclock_times[$BM_i];
    if ($BM_i < $BM_iters - 1) {
        echo ", ";
    }
}
echo "], [";
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    echo $BM_cycle_counts[$BM_i];
    if ($BM_i < $BM_iters - 1) {
        echo ", ";
    }
}
echo "], [";
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    echo $BM_aperf_counts[$BM_i];
    if ($BM_i < $BM_iters - 1) {
        echo ", ";
    }
}
echo "], [";
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    echo $BM_mperf_counts[$BM_i];
    if ($BM_i < $BM_iters - 1) {
        echo ", ";
    }
}
echo "]]\n";

?>
