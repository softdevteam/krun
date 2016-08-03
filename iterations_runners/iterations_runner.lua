local ffi = require("ffi")
ffi.cdef[[
    double clock_gettime_monotonic();
    double read_ts_reg_double();
]]
local kruntime = ffi.load("kruntime")

local BM_benchmark = arg[1]
local BM_iters = tonumber(arg[2])
local BM_param = tonumber(arg[3])
local BM_debug = tonumber(arg[4]) > 0

if #arg ~= 5 then
    print("usage: iterations_runner.lua <benchmark> <# of iterations> " ..
          "<benchmark param> <debug flag> <instrument flag>")
    os.exit(1)
end

dofile(BM_benchmark)

local BM_iter_times = {}
for BM_i = 1, BM_iters, 1 do
    BM_iter_times[BM_i] = 0
end

local BM_tsr_iter_times = {}
for BM_i = 1, BM_iters, 1 do
    BM_tsr_iter_times[BM_i] = 0
end

for BM_i = 1, BM_iters, 1 do
    if BM_debug then
        io.stderr:write(string.format("[iterations_runner.lua] iteration %d/%d\n", BM_i, BM_iters))
    end

    local BM_start_time = kruntime.clock_gettime_monotonic()
    local BM_tsr_start_time = kruntime.read_ts_reg_double();
    run_iter(BM_param) -- run one iteration of benchmark
    local BM_tsr_end_time = kruntime.read_ts_reg_double();
    local BM_end_time = kruntime.clock_gettime_monotonic()

    BM_iter_times[BM_i] = BM_end_time - BM_start_time
    BM_tsr_iter_times[BM_i] = BM_tsr_end_time - BM_tsr_start_time
end

io.stdout:write("[[")
for BM_i = 1, BM_iters, 1 do
    io.stdout:write(BM_iter_times[BM_i])
    if BM_i < BM_iters then
        io.stdout:write(", ")
    end
end
io.stdout:write("], [")
for BM_i = 1, BM_iters, 1 do
    io.stdout:write(BM_tsr_iter_times[BM_i])
    if BM_i < BM_iters then
        io.stdout:write(", ")
    end
end
io.stdout:write("]]\n")
