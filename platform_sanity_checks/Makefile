OS != uname

all: check_openbsd_malloc_options.so check_nice_priority.so

.PHONY: clean

check_openbsd_malloc_options.so: check_openbsd_malloc_options.c
	if [ "${OS}" = "OpenBSD" ]; then \
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -shared -Wall -Wextra -o \
		check_openbsd_malloc_options.so check_openbsd_malloc_options.c \
		; fi

check_nice_priority.so: check_nice_priority.c
	${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -shared -Wall -Wextra -o \
		check_nice_priority.so check_nice_priority.c

clean:
	rm -f check_openbsd_malloc_options.so check_nice_priority.so
