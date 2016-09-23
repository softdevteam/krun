<?php

/*
 * Note, you will need to patch the VM so as to allow access to:
 *  krun_init();
 *  krun_done();
 *  krun_measure();
 *  krun_get_num_cores();
 *  krun_get_wallclock();
 *  krun_get_{core_cycles,aperf,mperf}_double();
 */

if ($argc != 6) {
    fwrite(STDERR, "usage: iterations_runner.php <benchmark> <# of iterations> " .
           "<benchmark param> <debug flag> <instrument flag>\n");
    exit(1);
}

$BM_benchmark = $argv[1];
$BM_iters = $argv[2];
$BM_param = (int) $argv[3];
$BM_debug = ((int) $argv[4]) > 0;

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
$BM_wallclock_times = array_fill(0, $BM_iters, 0);
$BM_cycle_counts = array_fill(0, $BM_num_cores, array());
$BM_aperf_counts = array_fill(0, $BM_num_cores, array());
$BM_mperf_counts = array_fill(0, $BM_num_cores, array());
for ($BM_core = 0; $BM_core < $BM_num_cores; $BM_core++) {
    $BM_cycle_counts[$BM_core] = array_fill(0, $BM_iters, 0);
    $BM_aperf_counts[$BM_core] = array_fill(0, $BM_iters, 0);
    $BM_mperf_counts[$BM_core] = array_fill(0, $BM_iters, 0);
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
