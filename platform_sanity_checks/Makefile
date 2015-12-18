OS != uname

all: check_openbsd_malloc_options

.PHONY: clean

check_openbsd_malloc_options: check_openbsd_malloc_options.c
	if [ "${OS}" = "OpenBSD" ]; then \
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -shared -Wall -Wextra -o \
		check_openbsd_malloc_options check_openbsd_malloc_options.c \
		; fi

clean:
	rm -f check_openbsd_malloc_options
