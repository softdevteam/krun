// NOTE: you need to provide clock_gettime_monotonic.

/* Javascript has no assert() */
function _bench_assert(condition) {
    if (!condition) {
        throw "Assertion failed";
    }
}

if (this.arguments.length != 3) {
    throw "usage: iterations_runner.js <benchmark> <# of iterations> <benchmark param>";
}

entry_point = this.arguments[0];
n_iters = parseInt(this.arguments[1]);
param = parseInt(this.arguments[2]);

load(entry_point);

print("[");
for (i = 0; i < n_iters; i++) {
	//print("    Execution " + (i + 1) + "/" + n_iters); // XXX needs to got to stderr
	var start_time = clock_gettime_monotonic();
	run_iter(param);
	var stop_time = clock_gettime_monotonic();

	var intvl = stop_time - start_time;
	print(intvl);
	print(", ")
}
print("]");
