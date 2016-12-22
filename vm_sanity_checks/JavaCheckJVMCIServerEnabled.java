import java.lang.management.ManagementFactory;
import com.sun.management.HotSpotDiagnosticMXBean;
import com.sun.management.VMOption;

/**
 * Fake benchmark which crashes if Graal is not correctly enabled
 */
class JavaCheckJVMCIServerEnabled implements BaseKrunEntry {

    HotSpotDiagnosticMXBean diagBean;

    public static void main(String[] args) {
        new JavaCheckJVMCIServerEnabled().run_iter(666);
    }

    public JavaCheckJVMCIServerEnabled() {
        diagBean = ManagementFactory.getPlatformMXBean(HotSpotDiagnosticMXBean.class);
    }

    public void run_iter(int param) {
        /*
         * We want to know that:
         */

        /* A) The JVM was built with JVMCI support */
        String vmVers = System.getProperty("java.vm.version");
        if (!vmVers.contains("jvmci")) {
            String msg = "JVM was not built with JVMCI support: java.vm.version=" + vmVers;
            throw new java.lang.IllegalStateException(msg);
        }

        /* B) That JVMCI is enabled */
        String enableJVMCI = diagBean.getVMOption("EnableJVMCI").getValue();
        if (!enableJVMCI.equals("true")) {
            String msg = "JVMCI is not enabled: EnableJVMCI=" + enableJVMCI;
            throw new java.lang.IllegalStateException(msg);
        }

        /* C) The Graal compiler is selected */
        String useJVMCI = diagBean.getVMOption("UseJVMCICompiler").getValue();
        if (!useJVMCI.equals("true")) {
            String msg = "JVMCI compiler not selected: UseJVMCICompiler=" + useJVMCI;
            throw new java.lang.IllegalStateException(msg);
        }
    }
}
