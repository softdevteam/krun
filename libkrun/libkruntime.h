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

void libkruntime_init(void);
void libkruntime_done(void);

#ifdef __linux__
int get_fixed_pctr1_width(void);
int open_msr_node(int cpu);
void config_fixed_ctr1(int cpu, int enable);
void config_fixed_ctr1_all_cores(int enable);

uint64_t read_msr(int cpu, long addr);
uint64_t sum_msr_all_cores(long msr_addr, uint64_t mask);
void write_msr(int cpu, long addr, uint64_t msr_val);
void close_fd(int fd);
#endif // __linux__

uint64_t read_core_cycles(void);
uint64_t read_aperf(void);
uint64_t read_mperf(void);
double read_core_cycles_double(void);
double read_aperf_double(void);
double read_mperf_double(void);

double clock_gettime_monotonic(void);

double u64_to_double(uint64_t val);

#ifdef __cplusplus
}
#endif

#ifdef WITH_JAVA
JNIEXPORT void JNICALL Java_IterationsRunner_JNI_1libkruntime_1init(JNIEnv *e, jclass c);
JNIEXPORT void JNICALL Java_IterationsRunner_JNI_1libkruntime_1done(JNIEnv *e, jclass c);
JNIEXPORT jdouble JNICALL Java_IterationsRunner_JNI_1clock_1gettime_1monotonic(JNIEnv *e, jclass c);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1read_1core_1cycles(JNIEnv *e, jclass c);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1read_1aperf(JNIEnv *e, jclass c);
JNIEXPORT jlong JNICALL Java_IterationsRunner_JNI_1read_1mperf(JNIEnv *e, jclass c);
#endif  // WITH_JAVA

#endif  // __LIBKRUNTIME_H
