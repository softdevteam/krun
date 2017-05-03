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

if (this.arguments.length != 5) {
    throw "usage: iterations_runner.js <benchmark> <# of iterations> " +
          "<benchmark param> <debug flag> <instrument flag>";
}

var BM_entry_point = this.arguments[0];
var BM_n_iters = parseInt(this.arguments[1]);
var BM_param = parseInt(this.arguments[2]);
var BM_debug = parseInt(this.arguments[3]) > 0;

load(BM_entry_point);

krun_init();
var BM_num_cores = krun_get_num_cores();

// Pre-allocate and fill arrays
var BM_wallclock_times = new Array(BM_n_iters);
BM_wallclock_times.fill(0);

var BM_cycle_counts = new Array(BM_num_cores);
var BM_aperf_counts = new Array(BM_num_cores);
var BM_mperf_counts = new Array(BM_num_cores);

for (BM_core = 0; BM_core < BM_num_cores; BM_core++) {
    BM_cycle_counts[BM_core] = new Array(BM_n_iters);
    BM_aperf_counts[BM_core] = new Array(BM_n_iters);
    BM_mperf_counts[BM_core] = new Array(BM_n_iters);

    BM_cycle_counts[BM_core].fill(0);
    BM_aperf_counts[BM_core].fill(0);
    BM_mperf_counts[BM_core].fill(0);
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
