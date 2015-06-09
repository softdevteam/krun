all: java libkruntime

.PHONY: java libkruntime clean-java clean-libkruntime clean

java:
	cd krun/iteration_runners && javac *.java

libkruntime:
	cd libkruntime && ${MAKE}

clean: clean-java clean-libkruntime

clean-java:
	cd krun/iteration_runners && rm *.class

clean-libkruntime:
	cd libkruntime && ${MAKE} clean
