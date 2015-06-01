<?php

define('ANSI_MAGENTA', "\033[95m");
define('ANSI_RESET', "\033[0m");

/* PHP has a very small memory limit by default, crank */
ini_set('memory_limit', '8192M');

/*
 * Executes a benchmark many times within a single process.
 *
 * In Kalibera terms, this script represents one executions level run.
 */

class BenchTimer {
	private $start_time = -1.0;
	private $end_time = -1.0;

	function start() {
		$this->start_time = clock_gettime_monotonic();
	}

	function stop() {
		$this->stop_time = clock_gettime_monotonic();
		if ($this->start_time == -1) {
			throw new RuntimeException("timer was not started");
		}
	}

	function get() {
		if ($this->stop_time == -1) {
			throw new RuntimeException("timer was not stopped");
		}
		return $this->stop_time - $this->start_time;
	}
};

# main
if ($argc != 4) {
	echo "usage: iterations_runner.php <benchmark> <# of iterations> <benchmark param>\n";
	exit(1);
}

$BM_benchmark = $argv[1];
$BM_iters = $argv[2];
$BM_param = (int) $argv[3]; // parameter sent to benchmark.

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

echo "["; // we are going to print a Python eval-able list.
for ($BM_i = 0; $BM_i < $BM_iters; $BM_i++) {
        fprintf(STDERR, "    %sIteration %3d/%3d%s\n", ANSI_MAGENTA, $BM_i + 1, $BM_iters, ANSI_RESET);

	$timer = new BenchTimer();
	$timer->start();
	run_iter($BM_param);
	$timer->stop();

	echo $timer->get();
	echo ", ";
}
echo "]\n";

?>
