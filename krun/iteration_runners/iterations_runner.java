class BenchTimer {
    private long startTime, endTime;
    private boolean hasStarted = false, hasStopped = false;

    public void start() {
        // XXX is this monotonic?
        // http://docs.oracle.com/javase/1.5.0/docs/api/java/lang/System.html#nanoTime()
        hasStarted = true;
        startTime = System.nanoTime();
    }

    public void stop() {
        endTime = System.nanoTime();
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

class IterationRunner {
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
        //java.lang.reflect.Constructor<?> constructor = cls.getConstructor();

        System.out.print("[");
        for (int i = 0; i < iterations; i++) {
            System.err.println("    Execution: " + (i + 1) + "/" + iterations);

            //Object instance = constructor.newInstance();
            java.lang.reflect.Method method = cls.getMethod("run_iter", int.class);

            System.gc();
            BenchTimer t = new BenchTimer();

            t.start();
            //method.invoke(instance, param);
            // The entrypoint mus provide a static void method accepting one in arg called run_iter.
            method.invoke(null, param);
            t.stop();
            System.out.print(t.get() + ", ");
        }
        System.out.print("]");

    }
}
