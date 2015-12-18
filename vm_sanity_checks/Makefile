all: JavaCheckJVMCIServerEnabled.class

.PHONY: clean

JavaCheckJVMCIServerEnabled.class: JavaCheckJVMCIServerEnabled.java
	if [ "${ENABLE_JAVA}" = "1" ]; then \
		CLASSPATH=../iterations_runners/ ${JAVAC} \
		JavaCheckJVMCIServerEnabled.java; \
	fi

clean:
	rm -f *.class
