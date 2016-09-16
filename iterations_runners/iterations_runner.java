// Note:
// On Linux nanotime() calls clock_gettime() with the CLOCK_MONOTONIC flag.
// https://bugs.openjdk.java.net/browse/JDK-8006942
// This is not quite ideal. We should use CLOCK_MONOTONIC_RAW instead.
// For this reason we use JNI to make a call to clock_gettime() ourselves.

import java.util.Arrays;
import java.util.List;

// Instrumentation imports
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;
import java.lang.management.CompilationMXBean;
import java.lang.management.GarbageCollectorMXBean;


class KrunJDKInstrumentation {
    private CompilationMXBean compBean;

    public KrunJDKInstrumentation() {
        this.compBean = ManagementFactory.getCompilationMXBean();
    }

    // Emit cumulative compilation time in milliseconds to stderr
    private void getCompJSON(StringBuilder sb) {
        sb.append(this.compBean.getTotalCompilationTime());
    }


    /**
     * Write GC info for the specified collector bean to a StringBuilder.
     *
     * @param sb The StringBuilder to write to.
     * @param gcBean Collector in question
     *
     * Note, we resisted the temptation to use a mapping from name to info,
     * since it's not clear if names are always unique.
     */
    private void getGCJSON(StringBuilder sb, GarbageCollectorMXBean gcBean) {
        sb.append("[\"");
        sb.append(gcBean.getName());
        sb.append("\", ");

        // Memory pools
        sb.append("[");
        String[] poolNames = gcBean.getMemoryPoolNames();
        for (int i = 0; i < poolNames.length; i++) {
            sb.append('"');
            sb.append(poolNames[i]);
            sb.append('"');
            if (i < poolNames.length - 1) {
                sb.append(", ");
            }
        }
        sb.append("], ");

        // Collection time and counts
        sb.append(gcBean.getCollectionTime());
        sb.append(", ");
        sb.append(gcBean.getCollectionCount());

        sb.append("]");
    }

    /**
     * Write GC info for each collector to a StringBuilder
     *
     * @param sb The StringBuilder to write to.
     */
    private void getGCJSON(StringBuilder sb) {
        // Ask for a new list of collectors each time, in-case they change.
        List<GarbageCollectorMXBean> gcBeans =
            ManagementFactory.getGarbageCollectorMXBeans();

        sb.append("[");
        for (int i = 0; i < gcBeans.size(); i++) {
            GarbageCollectorMXBean gcBean = gcBeans.get(i);
            this.getGCJSON(sb, gcBean);
            if (i < gcBeans.size() - 1) {
                sb.append(", ");
            }
        }
        sb.append("]");
    }

    /**
     * Write a JSON compatible VM event line to a StringBuilder.
     *
     * The JSON is of the form:
     * [iterNum, cumuCompTime, collectorInfo]
     *
     * Where collectorInfo is a list of the form:
     * [collectorName, PoolNames, cumuCollectTime, cumuCollectCount]
     *
     * Here "cumu" means "cumulative" and times are in milliseconds.
     *
     * It is not clear if collectorNames are unique, so we assume they are not.
     *
     * Each collector manages one or more memory pools, and one memory
     * pool may be managed by multiple collectors.
     *
     * The JSON line is prefixed with a '@@@  JDK_EVENTS: '. Krun uses
     * this marker to locate instrumentation details.
     *
     * Example line:
     * @@@ JDK_EVENTS: [0, 17, [["PS Scavenge", ["PS Eden Space", "PS Survivor Space"], 0, 0]]]
     *
     * @param sb The StringBuilder to write to.
     * @param iterNum The iteration number we are emitting.
     */
    public void getInstJSON(StringBuilder sb, int iterNum) {
        sb.append("[");
        sb.append(iterNum);
        sb.append(", ");
        this.getCompJSON(sb);
        sb.append(", ");
        this.getGCJSON(sb);
        sb.append("]");
    }
}

// All entry points must implement this
interface BaseKrunEntry {
    public abstract void run_iter(int param);
}

class IterationsRunner {
    static {
        System.loadLibrary("kruntime");
    }

    public static native void JNI_libkruntime_init();
    public static native void JNI_libkruntime_done();
    public static native double JNI_clock_gettime_monotonic();
    public static native long JNI_read_core_cycles();
    public static native long JNI_read_aperf();
    public static native long JNI_read_mperf();

    public static void main(String args[]) throws
        ClassNotFoundException, NoSuchMethodException, InstantiationException, IllegalAccessException, java.lang.reflect.InvocationTargetException {

        if (args.length != 5) {
            System.out.println("usage: iterations_runner <benchmark> " +
                    "<# of iterations> <benchmark param> <debug flag>" +
                    "<instrument flag>\n");
            System.exit(1);
        }
        String benchmark = args[0];
        int iterations = Integer.parseInt(args[1]);
        int param = Integer.parseInt(args[2]);
        boolean debug = Integer.parseInt(args[3]) > 0;
        boolean instrument = Integer.parseInt(args[4]) > 0;

        KrunJDKInstrumentation krunInst = null;
        if (instrument) {
            krunInst = new KrunJDKInstrumentation();
        }

        StringBuilder sb = null;
        if (instrument) {
            // only instantiate if needed, and use the same one throughout
            sb = new StringBuilder();
        }

        // reflectively call the benchmark's run_iter
        Class<?> cls = Class.forName(benchmark);
        java.lang.reflect.Constructor<?>[] constructors = cls.getDeclaredConstructors();
        assert constructors.length == 1;
        Object instance = constructors[0].newInstance();
        BaseKrunEntry ke = (BaseKrunEntry) instance; // evil

        IterationsRunner.JNI_libkruntime_init();

        double[] wallclockTimes = new double[iterations];
        Arrays.fill(wallclockTimes, 0);

        /*
         * Core-cycle/aperf/mperf values are unsigned 64-bit, whereas Java long
         * is signed 64-bit. We are safe since:
         *
         *   - The only arithmetic we use is subtract, which is the same
         *     operation regardless of sign (due to two's compliment).
         *
         *   - Comaprisons use Long.compareUnsigned.
         *
         *   - We print the result using toUnsignedString, thus interpreting
         *     the number as unsigned.
         */
        long[] cycleCounts = new long[iterations];
        Arrays.fill(cycleCounts, 0);

        long[] aperfCounts = new long[iterations];
        Arrays.fill(aperfCounts, 0);

        long[] mperfCounts = new long[iterations];
        Arrays.fill(mperfCounts, 0);

        for (int i = 0; i < iterations; i++) {
            if (debug) {
                System.err.println("[iterations_runner.java] iteration: " + (i + 1) + "/" + iterations);
            }

            // Start timed section
            long mperfStart = IterationsRunner.JNI_read_mperf();
            long aperfStart = IterationsRunner.JNI_read_aperf();
            long cyclesStart = IterationsRunner.JNI_read_core_cycles();
            double wallclockStart = IterationsRunner.JNI_clock_gettime_monotonic();

            ke.run_iter(param);

            double wallclockStop = IterationsRunner.JNI_clock_gettime_monotonic();
            long cyclesStop = IterationsRunner.JNI_read_core_cycles();
            long aperfStop = IterationsRunner.JNI_read_aperf();
            long mperfStop = IterationsRunner.JNI_read_mperf();
            // End timed section

            // Instrumentation mode emits a JSON dict onto a marker line.
            if (instrument) {
                sb.append("@@@ JDK_EVENTS: ");
                krunInst.getInstJSON(sb, i);
                System.err.println(sb);
                System.err.flush();
                sb.setLength(0);  // clear
            }

            // Sanity checks
            if (wallclockStart > wallclockStop) {
                System.err.println("wallclock start is greater than stop");
                System.err.println("start=" + wallclockStart + " stop=" + wallclockStop);
                System.exit(1);
            }

            if (Long.compareUnsigned(cyclesStart, cyclesStop) > 0) {
                System.err.println("cycle count start is greater than stop");
                System.err.print("start=" + Long.toUnsignedString(cyclesStart) + " ");
                System.err.println("stop=" + Long.toUnsignedString(cyclesStop) + " ");
                System.exit(1);
            }

            if (Long.compareUnsigned(aperfStart, aperfStop) > 0) {
                System.err.println("aperf count start is greater than stop");
                System.err.print("start=" + Long.toUnsignedString(aperfStart) + " ");
                System.err.println("stop=" + Long.toUnsignedString(aperfStop) + " ");
                System.exit(1);
            }

            if (Long.compareUnsigned(mperfStart, mperfStop) > 0) {
                System.err.println("mperf count start is greater than stop");
                System.err.print("start=" + Long.toUnsignedString(mperfStart) + " ");
                System.err.println("stop=" + Long.toUnsignedString(mperfStop) + " ");
                System.exit(1);
            }

            // Compute deltas
            wallclockTimes[i] = wallclockStop - wallclockStart;
            cycleCounts[i] = cyclesStop - cyclesStart;
            aperfCounts[i] = aperfStop - aperfStart;
            mperfCounts[i] = mperfStop - mperfStart;
        }

        IterationsRunner.JNI_libkruntime_done();

        // Emit measurements
        System.out.print("[[");
        for (int i = 0; i < iterations; i++) {
            System.out.print(wallclockTimes[i]);

            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("], [");
        for (int i = 0; i < iterations; i++) {
            System.out.print(Long.toUnsignedString(cycleCounts[i]));

            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("], [");
        for (int i = 0; i < iterations; i++) {
            System.out.print(Long.toUnsignedString(aperfCounts[i]));

            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("], [");
        for (int i = 0; i < iterations; i++) {
            System.out.print(Long.toUnsignedString(mperfCounts[i]));

            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("]]");
    }
}
