class KrunEntry implements BaseKrunEntry {
    static {
        fannkuchredux.init();
    } // force class to be loaded

    public void run_iter(int param) {
        fannkuchredux.runIter(param);
    }
}
