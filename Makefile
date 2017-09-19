JAVAC ?= javac

PASS_DOWN_ARGS =	ENABLE_JAVA=${ENABLE_JAVA} JAVAC=${JAVAC} \
			JAVA_CPPFLAGS=${JAVA_CPPFLAGS} \
			JAVA_CFLAGS=${JAVA_CFLAGS} JAVA_LDFLAGS=${JAVA_LDFLAGS} \
			CC=${CC} CFLAGS=${CFLAGS} CPPFLAGS=${CPPFLAGS} \
			LDFLAGS=${LDFLAGS} NO_MSRS=${NO_MSRS}

.PHONY: utils libkrun vm-sanity-checks clean all

all: utils iterations-runners libkrun vm-sanity-checks platform-sanity-checks

iterations-runners: libkrun
	cd iterations_runners && ${MAKE} ${PASS_DOWN_ARGS}

libkrun:
	cd libkrun && ${MAKE} ${PASS_DOWN_ARGS}

vm-sanity-checks:
	cd vm_sanity_checks && ${MAKE} ${PASS_DOWN_ARGS}

platform-sanity-checks:
	cd platform_sanity_checks && ${MAKE} ${PASS_DOWN_ARGS}

utils:
	cd utils && ${MAKE}

clean:
	cd iterations_runners && ${MAKE} clean
	cd libkrun && ${MAKE} clean
	cd vm_sanity_checks && ${MAKE} clean
	cd platform_sanity_checks && ${MAKE} clean
	cd utils && ${MAKE} clean
