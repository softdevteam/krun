// XXX nanotime is actually CLOCK_MONOTONIC on linux, not MONOTONIC_RAW!
// https://bugs.openjdk.java.net/browse/JDK-8006942

// All entry points must implement this
interface BaseKrunEntry {
    public abstract void run_iter(int param);
}

class BenchTimer {
    private long startTime, endTime;
    private boolean hasStarted = false, hasStopped = false;

    public void start() {
        hasStarted = true;
        startTime = System.nanoTime(); // XXX almost monotonic
    }

    public void stop() {
        endTime = System.nanoTime(); // XXX almost monotonic
        assert(hasStarted);
        hasStopped = true;
    }

    public float get() {
        assert(hasStopped);
        // XXX check for integer/float pitfalls.
        float secs = (endTime - startTime) / (float) 1000000000; // One nano is 10^-9
        return secs;
    }
}

class IterationsRunner {
    public static void main(String args[]) throws
        ClassNotFoundException, NoSuchMethodException, InstantiationException, IllegalAccessException, java.lang.reflect.InvocationTargetException {

        if (args.length != 3) { // not 4 since java doesn't put the program name in args[0]
            System.out.println("usage: iterations_runner <benchmark> <# of iterations> <benchmark param>\n");
            System.exit(1);
        }
        String benchmark = args[0];
        int iterations = Integer.parseInt(args[1]);
        int param = Integer.parseInt(args[2]);

        // reflectively call the benchmark's run_iter
        Class<?> cls = Class.forName(benchmark);
        java.lang.reflect.Constructor<?>[] constructors = cls.getDeclaredConstructors();
        assert constructors.length == 1;
        Object instance = constructors[0].newInstance();
        BaseKrunEntry ke = (BaseKrunEntry) instance; // evil

        System.out.print("[");
        // Please, no refelction inside the timed code!
        for (int i = 0; i < iterations; i++) {
            System.err.println("    Execution: " + (i + 1) + "/" + iterations);

            BenchTimer t = new BenchTimer();
            t.start();
            ke.run_iter(param);
            t.stop();
            System.out.print(t.get() + ", ");
        }
        System.out.print("]");

    }
}
