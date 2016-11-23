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
    public abstract long run_iter(int param, long checksum);
}

class IterationsRunner {
    static {
        System.loadLibrary("kruntime");
    }

    public static native void JNI_krun_init();
    public static native void JNI_krun_done();
    public static native void JNI_krun_measure(int mindex);
    public static native double JNI_krun_get_wallclock(int mindex);
    public static native long JNI_krun_get_core_cycles(int mindex, int core);
    public static native long JNI_krun_get_aperf(int mindex, int core);
    public static native long JNI_krun_get_mperf(int mindex, int core);
    public static native int JNI_krun_get_num_cores();

    /* Prints signed longs for the per-core measurements */
    private static void emitPerCoreResults(String name, int numCores, long[][] array) {
        System.out.print("\"" + name + "\": [");

        for (int core = 0; core < numCores; core++) {
            System.out.print("[");
            for (int i = 0; i < array[core].length; i++) {
                System.out.print(Long.toUnsignedString(array[core][i]));

                if (i < array[core].length - 1) {
                    System.out.print(", ");
                }
            }
            System.out.print("]");
            if (core < numCores - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("]");
    }

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

        IterationsRunner.JNI_krun_init();
        int numCores = IterationsRunner.JNI_krun_get_num_cores();

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
        long[][] cycleCounts = new long[numCores][iterations];
        long[][] aperfCounts = new long[numCores][iterations];
        long[][] mperfCounts = new long[numCores][iterations];

        /* longs default to zero, but we explicitely zero to force allocation */
        for (int core = 0; core < numCores; core++) {
            Arrays.fill(cycleCounts[core], 0);
            Arrays.fill(aperfCounts[core], 0);
            Arrays.fill(mperfCounts[core], 0);
        }

        long checksum = 0;
        for (int i = 0; i < iterations; i++) {
            if (debug) {
                System.err.println("[iterations_runner.java] iteration: " + (i + 1) + "/" + iterations);
            }

            // Start timed section
            IterationsRunner.JNI_krun_measure(0);
            checksum += ke.run_iter(param, checksum);
            IterationsRunner.JNI_krun_measure(1);
            // End timed section

            // Instrumentation mode emits a JSON dict onto a marker line.
            if (instrument) {
                sb.append("@@@ JDK_EVENTS: ");
                krunInst.getInstJSON(sb, i);
                System.err.println(sb);
                System.err.flush();
                sb.setLength(0);  // clear
            }

            // Extract measurements
            wallclockTimes[i] = IterationsRunner.JNI_krun_get_wallclock(1) -
                IterationsRunner.JNI_krun_get_wallclock(0);

            for (int core = 0; core < numCores; core++) {
                cycleCounts[core][i] =
                    IterationsRunner.JNI_krun_get_core_cycles(1, core) -
                    IterationsRunner.JNI_krun_get_core_cycles(0, core);
                aperfCounts[core][i] =
                    IterationsRunner.JNI_krun_get_aperf(1, core) -
                    IterationsRunner.JNI_krun_get_aperf(0, core);
                mperfCounts[core][i] =
                    IterationsRunner.JNI_krun_get_mperf(1, core) -
                    IterationsRunner.JNI_krun_get_mperf(0, core);
            }
        }

        IterationsRunner.JNI_krun_done();

        // Emit measurements
        System.out.print("{");

        System.out.print("\"wallclock_times\": [");
        for (int i = 0; i < iterations; i++) {
            System.out.print(wallclockTimes[i]);
            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("], ");

        // per-core measurements
        IterationsRunner.emitPerCoreResults("core_cycle_counts", numCores, cycleCounts);
        System.out.print(", ");
        IterationsRunner.emitPerCoreResults("aperf_counts", numCores, aperfCounts);
        System.out.print(", ");
        IterationsRunner.emitPerCoreResults("mperf_counts", numCores, mperfCounts);

        System.out.print("}\n");
    }
}
