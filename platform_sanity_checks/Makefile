OS != uname

.PHONY: clean all

all: check_openbsd_malloc_options.so check_nice_priority.so \
	check_linux_cpu_affinity.so check_linux_scheduler.so

check_openbsd_malloc_options.so: check_openbsd_malloc_options.c
	if [ "${OS}" = "OpenBSD" ]; then \
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -shared -Wall -Wextra -o \
		check_openbsd_malloc_options.so check_openbsd_malloc_options.c \
		; fi

check_nice_priority.so: check_nice_priority.c
	${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_nice_priority.so check_nice_priority.c

check_linux_cpu_affinity.so: check_linux_cpu_affinity.c
	if [ "${OS}" = "Linux" ]; then \
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_linux_cpu_affinity.so check_linux_cpu_affinity.c \
		; fi

check_linux_scheduler.so: check_linux_scheduler.c
	if [ "${OS}" = "Linux" ]; then \
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_linux_scheduler.so check_linux_scheduler.c \
		; fi

clean:
	rm -f check_openbsd_malloc_options.so check_nice_priority.so \
		check_linux_cpu_affinity.so check_linux_scheduler.so
