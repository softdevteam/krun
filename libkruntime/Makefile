LIBKRUNTIME_CFLAGS =	-Wall -shared -fPIC

ifeq (${ENABLE_JAVA},1)
LIBKRUNTIME_CFLAGS += -DWITH_JAVA=1
endif

.PHONY: clean

all: libkruntime.so

libkruntime.so: libkruntime.c
	${CC} ${JAVA_CPPFLAGS} ${JAVA_CFLAGS} ${LIBKRUNTIME_CFLAGS} ${CFLAGS} \
		${CPPFLAGS} ${JAVA_LDFLAGS} ${LDFLAGS} libkruntime.c \
		-o libkruntime.so

clean:
	-rm libkruntime.so
