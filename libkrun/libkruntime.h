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

// Public API
void krun_init(void);
void krun_done(void);
void krun_measure(int mdata_idx);
double krun_get_wallclock(int mdata_idx);
uint64_t krun_get_core_cycles(int mdata_idx, int core);
uint64_t krun_get_aperf(int mdata_idx, int core);
uint64_t krun_get_mperf(int mdata_idx, int core);
double krun_get_core_cycles_double(int mdata_idx, int core);
double krun_get_aperf_double(int mdata_idx, int core);
double krun_get_mperf_double(int mdata_idx, int core);
int krun_get_num_cores(void);
void *krun_xcalloc(size_t nmemb, size_t size);

// The are not intended for general public use, but exposed for tests.
double krun_u64_to_double(uint64_t val);
double krun_clock_gettime_monotonic(void);
uint64_t krun_read_core_cycles(int core);

#ifdef __cplusplus
}
#endif

#ifdef WITH_JAVA
JNIEXPORT void JNICALL Java_IterationsRunner_JNI_1krun_1init(JNIEnv *e, jclass c);
JNIEXPORT void JNICALL Java_IterationsRunner_JNI_1krun_1done(JNIEnv *e, jclass c);
JNIEXPORT void JNICALL Java_IterationsRunner_JNI_1krun_1measure(JNIEnv *e, jclass c, jint mindex);
JNIEXPORT jdouble JNICALLJava_IterationsRunner_JNI_1krun_1get_1wallclock(JNIEnv *e, jclass c, jint mindex);
JNIEXPORT jdouble JNICALLJava_IterationsRunner_JNI_1krun_1clock_1gettime_1monotonic(JNIEnv *e, jclass c);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1krun_1get_1core_1cycles(JNIEnv *e, jclass c, jint mindex, jint core);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1krun_1get_1aperf(JNIEnv *e, jclass c, jint mindex, jint core);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1krun_1get_1mperf(JNIEnv *e, jclass c, jint mindex, jint core);
JNIEXPORT jint JNICALL Java_IterationsRunner_JNI_1krun_1get_1num_1cores(JNIEnv *e, jclass c);
#endif  // WITH_JAVA

#endif  // __LIBKRUNTIME_H
