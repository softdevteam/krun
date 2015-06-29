// XXX nanotime is actually CLOCK_MONOTONIC on linux, not MONOTONIC_RAW!
// https://bugs.openjdk.java.net/browse/JDK-8006942

// All entry points must implement this
interface BaseKrunEntry {
    public abstract void run_iter(int param);
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

            double startTime = System.nanoTime(); // XXX almost monotonic
            ke.run_iter(param);
            double stopTime = System.nanoTime(); // XXX almost monotonic

            double intvl = (stopTime - startTime) / (float) 1000000000; // nanosecs to secs
            System.out.print(intvl + ", ");
        }
        System.out.print("]");

    }
}
