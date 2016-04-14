/* Fake benchmark that checks the right scheduler and priority is used on Linux */

#include <stdio.h>
#include <stdlib.h>
#include <sched.h>
#include <err.h>

#define EXPECT_POLICY SCHED_FIFO

void
run_iter(int param) {
    int policy, rv, max_prio;
    struct sched_param s_param;

    (void) param;

    policy = sched_getscheduler(0);
    if (policy != EXPECT_POLICY) {
        fprintf(stderr, "Incorrect scheduler in use.\n");
        exit(EXIT_FAILURE);
    }

    max_prio = sched_get_priority_max(EXPECT_POLICY);

    rv = sched_getparam(0, &s_param);
    if (rv != 0) {
        perror("sched_getparam");
        exit(EXIT_FAILURE);
    }

    if (s_param.sched_priority != max_prio) {
        fprintf(stderr, "Wrong scheduler priority: expect %d, got %d.\n",
            max_prio, s_param.sched_priority);
        exit(EXIT_FAILURE);
    }
}
