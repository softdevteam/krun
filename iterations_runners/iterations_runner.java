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
    private String getCompJSON() {
        return "" + this.compBean.getTotalCompilationTime();
    }


    // Get GC info for the specified collector
    private String getGCJSON(GarbageCollectorMXBean gcBean) {
        String json = "[";

        // Memory pools
        json += "[";
        String[] poolNames = gcBean.getMemoryPoolNames();
        for (int i = 0; i < poolNames.length; i++) {
            json += '"' + poolNames[i] + '"';
            if (i < poolNames.length - 1) {
                json += ", ";
            }
        }
        json += "], ";

        // Collection time and counts
        json +=  gcBean.getCollectionTime() + ", ";
        json +=  gcBean.getCollectionCount();

        json += "]";
        return json;

    }

    // Get GC info for each collector
    private String getGCJSON() {
        // Ask for a new list of collectors each time, in-case they change.
        List<GarbageCollectorMXBean> gcBeans =
            ManagementFactory.getGarbageCollectorMXBeans();

        String json = "{";
        for (int i = 0; i < gcBeans.size(); i++) {
            GarbageCollectorMXBean gcBean = gcBeans.get(i);
            json += "\"" + gcBean.getName() + "\": " + this.getGCJSON(gcBean);
            if (i < gcBeans.size() - 1) {
                json += ", ";
            }
        }
        return json += "}";
    }

    /**
     * Build a JSON compatible string which Krun can parse in later.
     *
     * The JSON is of the form:
     * [iterNum, cumuCompTime, [collector1Info, ..., collectorNInfo]]
     *
     * Each collectorInfo record is of the form:
     * [collectorName: [[PoolName1, ..., PoolNameN],
     *                  cumuCollectTime, cumuCollectCount]
     *
     * Here "cumu" means "cumulative" and times are in milliseconds.
     *
     * Each collector manages one or more memory pools, and one memory
     * pool may be managed by multiple collectors.
     *
     * @param iterNum The iteration number we are emitting.
     */
    public String getInstJSON(int iterNum) {
        String json= "[" + iterNum + ", ";
        json += this.getCompJSON() + ", ";
        json += this.getGCJSON();
        json += "]";

        return json;
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
                System.err.println("@@@ JDK_EVENTS: " + krunInst.getInstJSON(i));
                System.err.flush();
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
