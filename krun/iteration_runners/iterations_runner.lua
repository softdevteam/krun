-- XXX os.clock() probably isn't good enough
-- http://www.lua.org/manual/5.3/manual.html#pdf-os.clock
-- http://codea.io/talk/discussion/360/milliseconds-in-codea-answered


-- Call out to C to get the monotonic time
local ffi = require("ffi")
ffi.cdef[[double clock_gettime_monotonic();]]
local kruntime = ffi.load("kruntime")

benchmark = arg[1]
iters = tonumber(arg[2])
param = tonumber(arg[3])

if #arg ~= 3 then
    print("usage: iterations_runner.lua <benchmark> <# of iterations> <benchmark param>")
    os.exit(1)
end

dofile(benchmark)

io.stdout:write("[")
io.stdout:flush()
for i = 1, iters, 1 do -- inclusive upper bound in lua
    io.stderr:write(string.format("    Iteration %d/%d\n", i, iters))

    start_time = kruntime.clock_gettime_monotonic()
    run_iter(param) -- run one iteration of benchmark
    end_time = kruntime.clock_gettime_monotonic()

    intvl = end_time - start_time
    io.stdout:write(intvl .. ", ")
    io.stdout:flush()
end

io.stdout:write("]")
io.stdout:flush()
