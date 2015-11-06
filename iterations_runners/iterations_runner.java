// Note:
// On Linux nanotime() calls clock_gettime() with the CLOCK_MONOTONIC flag.
// https://bugs.openjdk.java.net/browse/JDK-8006942
// This is not quite ideal. We should use CLOCK_MONOTONIC_RAW instead.
// For this reason we use JNI to make a call to clock_gettime() ourselves.

// All entry points must implement this
interface BaseKrunEntry {
    public abstract void run_iter(int param);
}

class IterationsRunner {
    static {
        System.loadLibrary("kruntime");
    }

    public static native double JNI_clock_gettime_monotonic();

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
            System.err.println("[iterations_runner.java] iteration: " + (i + 1) + "/" + iterations);

            double startTime = IterationsRunner.JNI_clock_gettime_monotonic();
            ke.run_iter(param);
            double stopTime = IterationsRunner.JNI_clock_gettime_monotonic();

            double intvl = (stopTime - startTime);
            System.out.print(intvl);

            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("]");

    }
}
