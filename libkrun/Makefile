LIBKRUNTIME_CFLAGS =	-Wall -shared -fPIC
COMMON_CFLAGS = -Wall -pedantic -std=gnu99

ifeq ("${TRAVIS}", "true")
	COMMON_CFLAGS += -DTRAVIS
endif

ifeq ($(shell uname -s),Linux)
	LIBKRUNTIME_LDFLAGS =	-lrt -ldl
else
	LIBKRUNTIME_LDFLAGS =
endif

ifeq (${ENABLE_JAVA},1)
LIBKRUNTIME_CFLAGS += -DWITH_JAVA=1
endif

.PHONY: clean

all: libkruntime.so test/test_prog

libkruntime.so: libkruntime.c libkruntime.h
	${CC} ${JAVA_CPPFLAGS} ${JAVA_CFLAGS} ${LIBKRUNTIME_CFLAGS} ${CFLAGS} \
		${CPPFLAGS} ${COMMON_CFLAGS} libkruntime.c -o libkruntime.so \
		${JAVA_LDFLAGS} ${LDFLAGS} ${LIBKRUNTIME_LDFLAGS}

test/test_prog: test/test_prog.c libkruntime.so
	${CC} ${CFLAGS} ${CPPFLAGS} ${COMMON_CFLAGS} test/test_prog.c \
		-o test/test_prog ${LDFLAGS} -L. -lkruntime -Wl,-rpath=$(shell pwd)

clean:
	rm -f libkruntime.so test/test_prog
