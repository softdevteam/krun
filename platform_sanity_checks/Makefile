OS = $(shell uname -s)

.PHONY: clean all

all: check_openbsd_malloc_options.so check_nice_priority.so \
	check_linux_cpu_affinity_pinned.so \
	check_linux_cpu_affinity_not_pinned.so \
	check_linux_scheduler.so

check_openbsd_malloc_options.so: check_openbsd_malloc_options.c
ifeq (${OS},OpenBSD)
	${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -shared -Wall -Wextra -o \
		check_openbsd_malloc_options.so check_openbsd_malloc_options.c
endif

check_nice_priority.so: check_nice_priority.c
	${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_nice_priority.so check_nice_priority.c

check_linux_cpu_affinity_pinned.so: check_linux_cpu_affinity_pinned.c
ifeq (${OS},Linux)
	${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_linux_cpu_affinity_pinned.so check_linux_cpu_affinity_pinned.c
endif

check_linux_cpu_affinity_not_pinned.so: check_linux_cpu_affinity_not_pinned.c
ifeq (${OS},Linux)
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_linux_cpu_affinity_not_pinned.so check_linux_cpu_affinity_not_pinned.c
endif

check_linux_scheduler.so: check_linux_scheduler.c
ifeq (${OS},Linux)
		${CC} ${CFLAGS} ${LDFLAGS} ${CPPFLAGS} -fPIC -shared -Wall -Wextra -o \
		check_linux_scheduler.so check_linux_scheduler.c
endif

clean:
	rm -f check_openbsd_malloc_options.so check_nice_priority.so \
		check_linux_cpu_affinity_pinned.so check_linux_scheduler.so \
		check_linux_cpu_affinity_not_pinned.so
