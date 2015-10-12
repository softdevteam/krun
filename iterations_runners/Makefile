PWD != pwd
C_ITER_RUNNER_CFLAGS = -fPIC -Wall -Wextra -pedantic
C_ITER_RUNNER_LDFLAGS =


OS != uname -s
ifeq ($(OS),Linux)
	C_ITER_RUNNER_LDFLAGS += -ldl
endif

.PHONY: clean

all: iterations_runner_c IterationsRunner.class BaseKrunEntry.class

IterationsRunner.class BaseKrunEntry.class: iterations_runner.java
	if [ "${ENABLE_JAVA}" = "1" ]; then \
		${JAVAC} iterations_runner.java; \
	fi

iterations_runner_c: iterations_runner.c
	${CC} ${C_ITER_RUNNER_CFLAGS} ${CFLAGS} -L${PWD}/../libkruntime \
		${CPPFLAGS} iterations_runner.c \
		-o iterations_runner_c -lkruntime ${C_ITER_RUNNER_LDFLAGS} \
		${LDFLAGS}

clean:
	-rm BaseKrunEntry.class IterationsRunner.class
	-rm iterations_runner_c
