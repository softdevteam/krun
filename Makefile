all: java libkruntime

.PHONY: java libkruntime clean-java clean-libkruntime clean

java:
	cd iterations_runners && javac *.java

libkruntime:
	cd libkruntime && ${MAKE} JAVA_CPPFLAGS=${JAVA_CPPFLAGS} \
		JAVA_CFLAGS=${JAVA_CFLAGS} JAVA_LDFLAGS=${JAVA_LDFLAGS}

clean: clean-java clean-libkruntime

clean-java:
	cd krun/iteration_runners && rm *.class

clean-libkruntime:
	cd libkruntime && ${MAKE} clean
