JAVAC ?= javac

PASS_DOWN_ARGS =	ENABLE_JAVA=${ENABLE_JAVA} JAVAC=${JAVAC} \
			JAVA_CPPFLAGS=${JAVA_CPPFLAGS} \
			JAVA_CFLAGS=${JAVA_CFLAGS} JAVA_LDFLAGS=${JAVA_LDFLAGS} \
			CC=${CC} CFLAGS=${CFLAGS} CPPFLAGS=${CPPFLAGS} \
			LDFLAGS=${LDFLAGS}

.PHONY: libkrun vm-sanity-checks clean all

all: iterations-runners libkrun vm-sanity-checks platform-sanity-checks rmsr/rmsr.ko

iterations-runners: libkrun
	cd iterations_runners && ${MAKE} ${PASS_DOWN_ARGS}

libkrun:
	cd libkrun && ${MAKE} ${PASS_DOWN_ARGS}

vm-sanity-checks:
	cd vm_sanity_checks && ${MAKE} ${PASS_DOWN_ARGS}

platform-sanity-checks:
	cd platform_sanity_checks && ${MAKE} ${PASS_DOWN_ARGS}

rmsr/rmsr.ko:
ifeq ($(shell uname -s),Linux)
ifneq ("${TRAVIS}","true")
	cd rmsr && ${MAKE}
endif
endif


clean:
	cd iterations_runners && ${MAKE} clean
	cd libkrun && ${MAKE} clean
	cd vm_sanity_checks && ${MAKE} clean
	cd platform_sanity_checks && ${MAKE} clean
	cd rmsr && ${MAKE} clean
