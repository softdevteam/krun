-- XXX os.clock() probably isn't good enough
-- http://www.lua.org/manual/5.3/manual.html#pdf-os.clock
-- http://codea.io/talk/discussion/360/milliseconds-in-codea-answered


-- Call out to C to get the monotonic time
local ffi = require("ffi")
ffi.cdef[[double clock_gettime_monotonic();]]
local kruntime = ffi.load("kruntime")

BM_benchmark = arg[1]
BM_iters = tonumber(arg[2])
BM_param = tonumber(arg[3])

if #arg ~= 3 then
    print("usage: iterations_runner.lua <benchmark> <# of iterations> <benchmark param>")
    os.exit(1)
end

dofile(BM_benchmark)

io.stdout:write("[")
io.stdout:flush()
for BM_i = 1, BM_iters, 1 do -- inclusive upper bound in lua
    io.stderr:write(string.format("[iterations_runner.lua] iteration %d/%d\n", BM_i, BM_iters))

    BM_start_time = kruntime.clock_gettime_monotonic()
    run_iter(BM_param) -- run one iteration of benchmark
    BM_end_time = kruntime.clock_gettime_monotonic()

    BM_intvl = BM_end_time - BM_start_time

    io.stdout:write(BM_intvl)
    if BM_i < BM_iters then
        io.stdout:write(", ")
    end

    io.stdout:flush()
end

io.stdout:write("]")
io.stdout:flush()
