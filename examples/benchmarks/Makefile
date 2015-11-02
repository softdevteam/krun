HERE !=		pwd
JAVAC ?=	javac

BENCHMARKS = dummy nbody

.PHONY: all clean

all:
	for i in ${BENCHMARKS}; do \
		echo "Building java benchmark $${i}..."; \
		cd ${HERE}/$${i}/java && \
		CLASSPATH=../../../../../krun/iterations_runners/ ${JAVAC} *.java; \
		done

clean:
	for i in ${BENCHMARKS}; do \
		cd ${HERE}/$${i}/java && \
		rm *.class; \
		done
