/* Javascript has no assert() */
function _bench_assert(condition) {
    if (!condition) {
        throw "Assertion failed";
    }
}

function BenchTimer() {

    this.start_time = null;
    this.stop_time = null;

    this.start = function() {
        _bench_assert(this.start_time == null);
        this.start_time = Date.now(); // XXX bad clock!
    };

    this.stop = function() {
        this.stop_time = Date.now(); // XXX bad clock!
        _bench_assert(this.start_time != null);
    };

    this.read = function() {
        _bench_assert(this.stop_time != null);
        return this.stop_time - this.start_time;
    };
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
	var tmr = new BenchTimer();
	tmr.start();
	run_iter(param);
	tmr.stop();
	print(tmr.read());
	print(", ")
}
print("]");
