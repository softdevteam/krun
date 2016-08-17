#ifndef __LIBKRUNTIME_H
#define __LIBKRUNTIME_H

#include <time.h>
#include <stdlib.h>
#include <errno.h>
#include <stdio.h>

#ifdef WITH_JAVA
#include <jni.h>
#endif // WITH_JAVA

#ifdef __cplusplus
extern "C" {
#endif

u_int64_t read_ts_reg_start();
u_int64_t read_ts_reg_stop();

double read_ts_reg_start_double();
double read_ts_reg_stop_double();

double read_ts_reg_start_double();
double clock_gettime_monotonic();

double u64_to_double(u_int64_t val);

#ifdef __cplusplus
}
#endif

#ifdef WITH_JAVA
JNIEXPORT jdouble JNICALL Java_IterationsRunner_JNI_1clock_1gettime_1monotonic(JNIEnv *e, jclass c);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1read_1ts_1reg_1start(JNIEnv *e, jclass c);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1read_1ts_1reg_1stop(JNIEnv *e, jclass c);
#endif  // WITH_JAVA

#endif  // __LIBKRUNTIME_H
