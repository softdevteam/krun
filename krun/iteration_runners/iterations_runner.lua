-- XXX os.clock() probably isn't good enough
-- http://www.lua.org/manual/5.3/manual.html#pdf-os.clock
-- http://codea.io/talk/discussion/360/milliseconds-in-codea-answered


-- Call out to C to get the monotonic time
local ffi = require("ffi")
ffi.cdef[[double clock_gettime_monotonic();]]
local kruntime = ffi.load("kruntime")

function new_timer()
    return {start_time=nil, end_time=nil}
end

function start_timer(tmr)
    tmr.start_time = kruntime.clock_gettime_monotonic();
end

function stop_timer(tmr)
    tmr.end_time = kruntime.clock_gettime_monotonic();
end

function read_timer(tmr)
    return tmr.end_time - tmr.start_time
end

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

    t = new_timer()
    collectgarbage()
    start_timer(t)
    run_iter(param) -- run one iteration of benchmark
    stop_timer(t)

    io.stdout:write(read_timer(t) .. ", ")
    io.stdout:flush()
end

io.stdout:write("]")
io.stdout:flush()
