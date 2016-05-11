LIBKRUNTIME_CFLAGS =	-Wall -shared -fPIC
LIBKRUNTIME_LDFLAGS =	-lrt -ldl

ifeq (${ENABLE_JAVA},1)
LIBKRUNTIME_CFLAGS += -DWITH_JAVA=1
endif

.PHONY: clean

all: libkruntime.so

libkruntime.so: libkruntime.c
	${CC} ${JAVA_CPPFLAGS} ${JAVA_CFLAGS} ${LIBKRUNTIME_CFLAGS} ${CFLAGS} \
		${CPPFLAGS} libkruntime.c -o libkruntime.so \
		${JAVA_LDFLAGS} ${LDFLAGS} ${LIBKRUNTIME_LDFLAGS}\

clean:
	rm -f libkruntime.so
