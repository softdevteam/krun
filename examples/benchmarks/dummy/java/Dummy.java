public final class Dummy {

    private static final int DELAY = 1000;  // milliseconds.

    /** The benchmark itself. */
    private static void dummy() {
        try {
            Thread.sleep(DELAY);
        } catch (InterruptedException e) {
            System.out.println("Benchmark was interrupted.");
            System.out.println("Measurements may be inaccurate.");
        }
    }

    /** Entry point to the benchmark.
     * This method is called by krun and runs one iteration of the benchmark.
     */
    public static void runIter(int n) {
        Dummy.dummy();
    }

}
