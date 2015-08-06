HERE != pwd
ITERATIONS_RUNNERS_DIR = ${HERE}/iterations_runners

all: iterations-runners libkruntime vm-sanity-checks

.PHONY: iterations-runners libkruntime clean-iterations-runners
.PHONY: clean-libkruntime clean-vm-sanity-checks clean

iterations-runners:
	cd iterations_runners && javac *.java

libkruntime:
	cd libkruntime && ${MAKE} JAVA_CPPFLAGS=${JAVA_CPPFLAGS} \
		JAVA_CFLAGS=${JAVA_CFLAGS} JAVA_LDFLAGS=${JAVA_LDFLAGS}

vm-sanity-checks:
	cd vm_sanity_checks && \
		CLASSPATH=${ITERATIONS_RUNNERS_DIR} javac *.java

clean: clean-iterations-runners clean-libkruntime

clean-iterations-runners:
	cd krun/iteration_runners && rm *.class

clean-vm-sanity-checks:
	cd krun/vm_sanity_checks && rm *.class

clean-libkruntime:
	cd libkruntime && ${MAKE} clean
