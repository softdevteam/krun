LIBKRUNTIME_CFLAGS =	-Wall -shared -fPIC
COMMON_CFLAGS = -Wall -pedantic -std=gnu99
SUDO = sudo

# Sadly this tool requires root
VIRT_WHAT = ${SUDO} /usr/sbin/virt-what

# Detect if we are virtualised (Linux only for now XXX)
ifeq ($(shell uname -s),Linux)
	VIRTUALISED = 0  # default off

	VIRT_FACTS = $(shell ${VIRT_WHAT})
	ifneq ("${VIRT_FACTS}","")
		VIRTUALISED = 1
	endif

	ifeq ("${TRAVIS}","true")
		VIRTUALISED = 1
	endif

	# Under virtualised conditions, we have no performance counters.
	# MSR-centric code is also guarded on a per-OS basis in libkruntime.c
	ifeq (${VIRTUALISED},1)
		COMMON_CFLAGS += -DNO_MSRS
	else ifeq (${NO_MSRS},1)
		# You can also force off MSR support. This can be useful for
		# testing on machines without the Krun Linux kernel installed.
		COMMON_CFLAGS += -DNO_MSRS
	endif
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
