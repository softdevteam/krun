EXTRA_CFLAGS=-Wall

all: libkruntime.so

libkruntime.so: libkruntime.c
	${CC} ${JAVA_CPPFLAGS} ${JAVA_CFLAGS} ${EXTRA_CFLAGS} ${CFLAGS} \
		${CPPFLAGS} ${JAVA_LDFLAGS} ${LDFLAGS} -shared -fPIC \
		libkruntime.c -o libkruntime.so

.PHONY: clean
clean:
	rm libkruntime.so
