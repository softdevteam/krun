JAVAC ?=	javac

BENCHMARKS = fannkuch_redux nbody

BENCH_CFLAGS =    -shared -Wall -fPIC -m64
BENCH_LDFLAGS =
C_EXTRA_LDFLAGS_nbody = -lm

.PHONY: all c-bench java-bench clean clean-c clean-java

all: c-bench

c-bench:
	$(foreach i, ${BENCHMARKS}, \
		echo "Building C benchmark ${i}..."; \
		cd ${i}/c && \
		${CC} ${CFLAGS} ${CPPFLAGS} ${BENCH_CFLAGS} -o bench.so bench.c \
		${LDFLAGS} ${BENCH_LDFLAGS} ${C_EXTRA_LDFLAGS_${i}} || exit $?; \
		cd ../../; \
	)

java-bench:
	$(foreach i, ${BENCHMARKS}, \
		echo "Building java benchmark ${i}..."; \
		cd ${i}/java && \
		CLASSPATH=../../../../iterations_runners/ ${JAVAC} *.java; \
		cd ../../; \
	)

clean: clean-java clean-c

clean-java:
	$(foreach i, ${BENCHMARKS}, \
		cd ${i}/java && \
		rm -f *.class; \
		cd ../../; \
	)

clean-c:
	$(foreach i, ${BENCHMARKS}, \
		cd  ${i}/c && \
		rm -f *.so; \
		cd ../../; \
	)
