JAVAC ?= javac

PASS_DOWN_ARGS =	ENABLE_JAVA=${ENABLE_JAVA} JAVAC=${JAVAC} \
			JAVA_CPPFLAGS=${JAVA_CPPFLAGS} \
			JAVA_CFLAGS=${JAVA_CFLAGS} JAVA_LDFLAGS=${JAVA_LDFLAGS} \
			CC=${CC} CFLAGS=${CFLAGS} CPPFLAGS=${CPPFLAGS} \
			LDFLAGS=${LDFLAGS}

.PHONY: libkruntime vm-sanity-checks clean

all: iterations-runners libkruntime vm-sanity-checks

iterations-runners: libkruntime
	cd iterations_runners && ${MAKE} ${PASS_DOWN_ARGS}

libkruntime:
	cd libkruntime && ${MAKE} ${PASS_DOWN_ARGS}

vm-sanity-checks:
	cd vm_sanity_checks && ${MAKE} ${PASS_DOWN_ARGS}

clean:
	cd iterations_runners && ${MAKE} clean
	cd libkruntime && ${MAKE} clean
	cd vm_sanity_checks && ${MAKE} clean
