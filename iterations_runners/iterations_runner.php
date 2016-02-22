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
if ($argc != 5) {
	echo "usage: iterations_runner.php <benchmark> <# of iterations> <benchmark param> <debug flag>\n";
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

/* OK, all is well, let's run. */

echo "["; // we are going to print a JSON list.
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
    if ($BM_debug) {
        fprintf(STDERR, "[iterations_runner.php] iteration %d/%d\n", $BM_i + 1, $BM_iters);
    }

	$start_time = clock_gettime_monotonic();
	run_iter($BM_param);
	$stop_time = clock_gettime_monotonic();

	echo $stop_time - $start_time;
    if ($BM_i < $BM_iters - 1) {
        echo ", ";
    }
}
echo "]\n";

?>
