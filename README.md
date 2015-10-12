# Krun

Soft-dev benchmark runner.

## Build Instructions

Run GNU make.

The build system honours the standard variables: CC, CPPFLAGS, CFLAGS and
LDFLAGS.

To build with Java support, set:

 * `ENABLE_JAVA` to `1`
 * `JAVA_CPPFLAGS` to specify paths to include dirs for Java (i.e. `-I<path>`).
 * `JAVA_LDFLAGS` to specify paths to lib dirs for Java (i.e. `-L<path>`).
 * `JAVAC` if you want to specify a Java compiler other than the system default.
 * `JAVA_CFLAGS` to specify any extra CFLAGS to build against Java VM.

e.g.:

```
make JAVA_CPPFLAGS='"-I${JAVA_HOME}/include -I${JAVA_HOME}/include/linux"' \
    JAVA_LDFLAGS=-L${JAVA_HOME}/lib ENABLE_JAVA=1
```
