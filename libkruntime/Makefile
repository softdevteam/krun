EXTRA_CFLAGS=-Wall -Wextra

all: libkruntime.so

libkruntime.so: libkruntime.c
	${CC} ${EXTRA_CFLAGS} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -shared -fPIC libkruntime.c -o libkruntime.so

.PHONY: clean
clean:
	rm libkruntime.so
