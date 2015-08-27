// NOTE: you need to provide clock_gettime_monotonic.

if (this.arguments.length != 3) {
    throw "usage: iterations_runner.js <benchmark> <# of iterations> <benchmark param>";
}

var BM_entry_point = this.arguments[0];
var BM_n_iters = parseInt(this.arguments[1]);
var BM_param = parseInt(this.arguments[2]);

load(BM_entry_point);

print("[");
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
	print_err("[iterations_runner.js] iteration " + (BM_i + 1) + "/" + BM_n_iters);
	var BM_start_time = clock_gettime_monotonic();
	run_iter(BM_param);
	var BM_stop_time = clock_gettime_monotonic();

	var BM_intvl = BM_stop_time - BM_start_time;
	print(BM_intvl);
    if (BM_i < BM_n_iters - 1) {
        print(", ")
    }
}
print("]");
