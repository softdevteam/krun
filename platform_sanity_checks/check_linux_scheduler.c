/* Fake benchmark that checks the right scheduling policy is used on Linux */

#include <stdio.h>
#include <stdlib.h>
#include <sched.h>
#include <err.h>

#define EXPECT_POLICY SCHED_OTHER

void
run_iter(int param) {
    int policy;

    (void) param;

    policy = sched_getscheduler(0);
    if (policy != EXPECT_POLICY) {
        fprintf(stderr, "Incorrect scheduler in use.\n");
        exit(EXIT_FAILURE);
    }
}
