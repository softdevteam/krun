JAVAC ?=	javac

BENCHMARKS = dummy nbody

.PHONY: all clean

all:
	$(foreach i, ${BENCHMARKS}, \
		echo "Building java benchmark ${i}..."; \
		cd ${i}/java && \
		CLASSPATH=../../../../iterations_runners/ ${JAVAC} *.java; \
		cd ../../; \
	)

clean:
	$(foreach i, ${BENCHMARKS}, \
		cd ${i}/java && \
		rm *.class; \
		cd ../../ \
	)
