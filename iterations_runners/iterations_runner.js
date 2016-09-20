// NOTE: JS VM will need to be patched to allow access to:
//
//   libkruntime_init()
//   libkruntime_done()
//   clock_gettime_monotonic()
//   read_core_cycles_double()
//   read_aperf_double()
//   read_mperf_double()

if (this.arguments.length != 5) {
    throw "usage: iterations_runner.js <benchmark> <# of iterations> " +
          "<benchmark param> <debug flag> <instrument flag>";
}

var BM_entry_point = this.arguments[0];
var BM_n_iters = parseInt(this.arguments[1]);
var BM_param = parseInt(this.arguments[2]);
var BM_debug = parseInt(this.arguments[3]) > 0;

load(BM_entry_point);

// Pre-allocate and fill arrays
var BM_wallclock_times = new Array(BM_n_iters);
BM_wallclock_times.fill(0);

var BM_cycle_counts = new Array(BM_n_iters);
BM_cycle_counts.fill(0);

var BM_aperf_counts = new Array(BM_n_iters);
BM_aperf_counts.fill(0);

var BM_mperf_counts = new Array(BM_n_iters);
BM_mperf_counts.fill(0);

libkruntime_init();

// Main loop
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    if (BM_debug) {
        print_err("[iterations_runner.js] iteration " + (BM_i + 1) + "/" + BM_n_iters);
    }

    // Start timed section
    var BM_mperf_start = read_mperf_double();
    var BM_aperf_start = read_aperf_double();
    var BM_cycles_start = read_core_cycles_double();
    var BM_wallclock_start = clock_gettime_monotonic();

    run_iter(BM_param);

    var BM_wallclock_stop = clock_gettime_monotonic();
    var BM_cycles_stop = read_core_cycles_double();
    var BM_aperf_stop = read_aperf_double();
    var BM_mperf_stop = read_mperf_double();
    // End timed section

    // Sanity checks
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

    if (BM_aperf_start > BM_aperf_stop) {
        print_err("aperf start greater than stop");
        print_err("start=" + BM_aperf_start + " stop=" + BM_aperf_stop);
        throw("fail");
    }

    if (BM_mperf_start > BM_mperf_stop) {
        print_err("mperf start greater than stop");
        print_err("start=" + BM_mperf_start + " stop=" + BM_mperf_stop);
        throw("fail");
    }

    // Compute deltas
    BM_wallclock_times[BM_i] = BM_wallclock_stop - BM_wallclock_start;
    BM_cycle_counts[BM_i] = BM_cycles_stop - BM_cycles_start;
    BM_aperf_counts[BM_i] = BM_aperf_stop - BM_aperf_start;
    BM_mperf_counts[BM_i] = BM_mperf_stop - BM_mperf_start;
}

libkruntime_done();

// Emit measurements
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
write("], [");
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    write(BM_aperf_counts[BM_i]);

    if (BM_i < BM_n_iters - 1) {
        write(", ")
    }
}
write("], [");
for (BM_i = 0; BM_i < BM_n_iters; BM_i++) {
    write(BM_mperf_counts[BM_i]);

    if (BM_i < BM_n_iters - 1) {
        write(", ")
    }
}
write("]]\n");
