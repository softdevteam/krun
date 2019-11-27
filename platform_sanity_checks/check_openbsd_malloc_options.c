#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define EXPECT_OPTS     "cfgrux"

void
run_iter(int param)
{
    char        *malloc_opts;

    (void) param;  /* silence compiler warning */

    malloc_opts = getenv("MALLOC_OPTIONS");
    if ((malloc_opts == NULL) || (strcmp(malloc_opts, EXPECT_OPTS) != 0)) {
        fprintf(stderr, "malloc opts not set or not '%s'\n", EXPECT_OPTS);
        exit(EXIT_FAILURE);
    }
}
