/* Dummy benchmark.
 * Each iteration sleeps for one second.
 */
#include <unistd.h>

#define DELAY 1 /* second. */

/* The benchmark itself. */
void dummy() {
    sleep(DELAY);
}

/* Entry point to the benchmark.
 * This method is called by krun and runs one iteration of the benchmark.
 */
void run_iter(int n) {
    dummy();
}
