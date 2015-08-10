class JavaCheckJVMCIServerEnabled implements BaseKrunEntry {
    public static void main(String[] args) {
        new JavaCheckJVMCIServerEnabled().run_iter(666);
    }

    public void run_iter(int param) {
        /* Crash if JVMCI is not present */
        String vm_name = System.getProperty("java.vm.name");

        if (!vm_name.contains("JVMCI")) {
            String msg = "JVMCI server was not enabled.";
            throw new java.lang.IllegalStateException(msg);
        }
    }
}
