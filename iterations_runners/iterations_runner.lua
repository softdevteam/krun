local ffi = require("ffi")
ffi.cdef[[
    double libkruntime_init(void);
    double libkruntime_done(void);
    double clock_gettime_monotonic(void);
    double read_core_cycles_double(void);
]]
local kruntime = ffi.load("kruntime")

local BM_benchmark = arg[1]
local BM_iters = tonumber(arg[2])
local BM_param = tonumber(arg[3])
local BM_debug = tonumber(arg[4]) > 0

if #arg ~= 5 then
    io.stderr:write("usage: iterations_runner.lua <benchmark> <# of iterations> " ..
                    "<benchmark param> <debug flag> <instrument flag>")
    os.exit(1)
end

dofile(BM_benchmark)

local BM_wallclock_times = {}
for BM_i = 1, BM_iters, 1 do
    BM_wallclock_times[BM_i] = 0
end

local BM_cycle_counts = {}
for BM_i = 1, BM_iters, 1 do
    BM_cycle_counts[BM_i] = 0
end

kruntime.libkruntime_init()

for BM_i = 1, BM_iters, 1 do
    if BM_debug then
        io.stderr:write(string.format("[iterations_runner.lua] iteration %d/%d\n", BM_i, BM_iters))
    end

    local BM_cycles_start = kruntime.read_core_cycles_double();
    local BM_wallclock_start = kruntime.clock_gettime_monotonic()
    run_iter(BM_param) -- run one iteration of benchmark
    local BM_wallclock_stop = kruntime.clock_gettime_monotonic()
    local BM_cycles_stop = kruntime.read_core_cycles_double()

    if BM_wallclock_start > BM_wallclock_stop then
        io.stderr:write("wallclock start is greater than stop\n")
        io.stderr:write(String.format("start=%d stop=%d\n", BM_wallclock_start, BM_wallclock_stop))
        os.exit(1)
    end

    if BM_cycles_start > BM_cycles_stop then
        io.stderr:write("cycles start is greater than stop\n")
        io.stderr:write(String.format("start=%d stop=%d\n", BM_cycles_start, BM_cycles_stop))
        os.exit(1)
    end

    BM_wallclock_times[BM_i] = BM_wallclock_stop - BM_wallclock_start
    BM_cycle_counts[BM_i] = BM_cycles_stop - BM_cycles_start
end

kruntime.libkruntime_done()

io.stdout:write("[[")
for BM_i = 1, BM_iters, 1 do
    io.stdout:write(BM_wallclock_times[BM_i])
    if BM_i < BM_iters then
        io.stdout:write(", ")
    end
end
io.stdout:write("], [")
for BM_i = 1, BM_iters, 1 do
    io.stdout:write(BM_cycle_counts[BM_i])
    if BM_i < BM_iters then
        io.stdout:write(", ")
    end
end
io.stdout:write("]]\n")
