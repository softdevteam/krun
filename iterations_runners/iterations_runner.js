// NOTE: JS VM will need to be patched to allow access to:
//
//   libkruntime_init()
//   libkruntime_done()
//   clock_gettime_monotonic()
//   read_core_cycles_double()

if (this.arguments.length != 5) {
    throw "usage: iterations_runner.js <benchmark> <# of iterations> " +
          "<benchmark param> <debug flag> <instrument flag>";
}

var BM_entry_point = this.arguments[0];
var BM_n_iters = parseInt(this.arguments[1]);
var BM_param = parseInt(this.arguments[2]);
var BM_debug = parseInt(this.arguments[3]) > 0;

load(BM_entry_point);

var BM_wallclock_times = new Array(BM_n_iters);
BM_wallclock_times.fill(0);

var BM_cycle_counts = new Array(BM_n_iters);
BM_cycle_counts.fill(0);

libkruntime_init();

for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    if (BM_debug) {
        print_err("[iterations_runner.js] iteration " + (BM_i + 1) + "/" + BM_n_iters);
    }

    var BM_cycles_start = read_core_cycles_double();
    var BM_wallclock_start = clock_gettime_monotonic();
    run_iter(BM_param);
    var BM_wallclock_stop = clock_gettime_monotonic();
    var BM_cycles_stop = read_core_cycles_double();

    if (BM_wallclock_start > BM_wallclock_stop) {
        print_err("wallclock start greater than stop");
        print_err("start=" + BM_wallclock_start + " stop=" + BM_wallclock_stop);
        throw("fail");
    }

    if (BM_cycles_start > BM_cycles_stop) {
        print_err("cycle count start greater than stop");
        print_err("start=" + BM_cycles_start + " stop=" + BM_cycles_stop);
        throw("fail");
    }

    BM_wallclock_times[BM_i] = BM_wallclock_stop - BM_wallclock_start;
    BM_cycle_counts[BM_i] = BM_cycles_stop - BM_cycles_start;
}

libkruntime_done();

write("[[");
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    write(BM_wallclock_times[BM_i]);

    if (BM_i < BM_n_iters - 1) {
        write(", ")
    }
}
write("], [");
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    write(BM_cycle_counts[BM_i]);

    if (BM_i < BM_n_iters - 1) {
        write(", ")
    }
}
write("]]\n");
