C_ITER_RUNNER_CFLAGS = -fPIC -Wall -Wextra -pedantic -std=gnu99

ifeq ($(shell uname -s),Linux)
	C_ITER_RUNNER_LDFLAGS = -ldl -lrt
else
	C_ITER_RUNNER_LDFLAGS =
endif

.PHONY: clean

all: iterations_runner_c IterationsRunner.class BaseKrunEntry.class

IterationsRunner.class BaseKrunEntry.class: iterations_runner.java
	if [ "${ENABLE_JAVA}" = "1" ]; then \
		${JAVAC} iterations_runner.java; \
	fi

iterations_runner_c: iterations_runner.c
	echo ${C_ITER_RUNNER_LDFLAGS}
	${CC} ${C_ITER_RUNNER_CFLAGS} ${CFLAGS} -L`pwd`/../libkrun \
		${CPPFLAGS} iterations_runner.c \
		-o iterations_runner_c -lkruntime ${C_ITER_RUNNER_LDFLAGS} \
		${LDFLAGS}

clean:
	rm -f BaseKrunEntry.class IterationsRunner.class
	rm -f iterations_runner_c
