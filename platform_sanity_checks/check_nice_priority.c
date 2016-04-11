/* Fake benchmark that checks we are running in high priority */

#include <stdio.h>
#include <sys/resource.h>
#include <sys/time.h>
#include <stdlib.h>

#define EXPECT_PRIORITY -20

void
run_iter(int param) {
    int prio = getpriority(PRIO_PROCESS, 0);

    (void) param;

    if (prio != EXPECT_PRIORITY) {
        fprintf(stderr, "process priority: expect %d got %d\n", EXPECT_PRIORITY, prio);
        exit(EXIT_FAILURE);
    }
}
