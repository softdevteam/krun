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

    public static native double JNI_clock_gettime_monotonic();

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

        double[] iter_times = new double[iterations];
        Arrays.fill(iter_times, -1.0);

        // Please, no refelction inside the timed code!
        for (int i = 0; i < iterations; i++) {
            if (debug) {
                System.err.println("[iterations_runner.java] iteration: " + (i + 1) + "/" + iterations);
            }

            double startTime = IterationsRunner.JNI_clock_gettime_monotonic();
            ke.run_iter(param);
            double stopTime = IterationsRunner.JNI_clock_gettime_monotonic();

            // Instrumentation mode emits a JSON dict onto a marker line.
            if (instrument) {
                sb.append("@@@ JDK_EVENTS: ");
                krunInst.getInstJSON(sb, i);
                System.err.println(sb);
                System.err.flush();
                sb.setLength(0);  // clear
            }

            iter_times[i] = stopTime - startTime;
        }

        System.out.print("[");
        for (int i = 0; i < iterations; i++) {
            System.out.print(iter_times[i]);

            if (i < iterations - 1) {
                System.out.print(", ");
            }
        }
        System.out.print("]\n");
    }
}
