# Krun

Krun is a framework for running software benchmarking experiments.

**Krun uses sudo to elevate privileges! Please read these instructions in
full.**

The `examples/` directory contains a simple experiment using Krun.
This is a good starting point for setting up your own Krun configuration.

The example here contains two benchmark programs (*nbody* and *dummy*),
executed on two VMs (*cPython* and native code with no VM). There is a separate
example with Java (using *JVM* such as HotSpot), which requires you to set up
some environment variables before you compile Krun.
Each benchmark is run for 5 iterations on the same VM, then the VM is
restarted and the benchmark is re-run for another 5 iterations.
We say that the experiment runs 2 *process executions* and 5 *in-process iterations* of
each benchmark.

This configuration can be found in the file `examples/example.krun`. The
example with Java can be found in `examples/java.krun`.

## Step 1: prepare the benchmarking machine

Krun currently only runs on Unix-like environments.
To run this example experiment, you need superuser rights to the machine you are
using, e.g. on Linux you should be able to run `sudo`.

### Dependencies

Krun currently runs on (Debian) Linux and OpenBSD.

You need to have the following installed:

  * Python2.7 (pre-installed in Debian)
  * GNU make, a C compiler and libc (`build-essential` package in Debian)
  * cpufrequtils (Linux only. `cpufrequtils` package in Debian)
  * cffi (`python-cffi` package in Debian)
  * cset (for pinning on Linux only. `cpuset` package in Debian)
  * virt-what (Linux only. `virt-what` package in Debian)
  * Our custom Linux kernel (see below).
  * Linux kernel headers (Linux only. linux-headers-3... in Debian)
  * taskset (Linux only)
  * msr-tools (Linux only)

If you want to benchmark Java, you will also need:
  * A Java SDK 7 (`openjdk-7-jdk` package in Debian)

Note that to use pinning on Linux, `cset shield` must be in a working state.
Some Linux distributions have been known to ship with this functionality
broken. See the `cset` tutorial for information on how to test `cset shield`:
https://rt.wiki.kernel.org/index.php/Cpuset_Management_Utility/tutorial

### Kernel arguments

If you are using a Linux system, you will need to set a kernel arguments to
disable Intel P-states. If your Linux bootloader is Grub, you can follow these
steps:

  * Edit /etc/default/grub (e.g. `sudo gedit /etc/default/grub`)
  * Add `intel_pstate=disable` to `GRUB_CMDLINE_LINUX_DEFAULT`
  * Run `sudo update-grub`

You can disable Krun's P-state check with `--disable-pstate-check`, however
this is strongly discouraged for real benchmarking.

### The Krun Linux Kernel

When Krun is run on Linux it requires a custom Linux Kernel which offers low
latency access to the `IA32_APERF`, `IA32_MPERF` and `IA32_PERF_FIXED_CTR1`
MSRs (sadly `IA32_APERF` or `IA32_MPERF` cannot be read from user-space via
`rdpmc` and `rdmsr` is strictly a ring 0 operation). The kernel must also be
configured to be tickless on all CPU cores except the boot core.

Instructions and source code can be found here:
https://github.com/softdevteam/krun-linux-kernel

#### Benchmarking on a Stock Linux Kernel

You can run Krun on a stock Linux Kernel, but Krun will be unable to
collect data from:

  * IA32_PERF_FIXED_CTR1 (the core cycle counter)
  * IA32_APERF counts
  * IA32_MPERF counts

Since these are highly useful metrics, we strongly advise against using a stock
Linux kernel for real benchmarking.

With the above warning in mind, to run on a stock Linux kernel, when building
Krun, include `NO_MSRS=1` in your environment.

## Step 2: Fetch the Krun source

```bash
$ git clone --recursive https://github.com/softdevteam/krun.git
$ cd krun
```

## Step 3: Build Krun

The Krun Makefile honours the standard variables: `CC`, `CPPFLAGS`, `CFLAGS`
and `LDFLAGS`. For example, if you wish to use `clang` rather than `gcc` you
can append `CC=clang` to the `make` command below. You should build Krun
by invoking GNU make:

```bash
$ pwd
.../Krun
$ make  # gmake on non-Linux platforms.
```

If you want to benchmark Java programs, you will also need to set the
`JAVA_HOME` environment variable, and build Krun with some extra flags. The
invocation below comes from a Ubuntu Linux machine, you may need to replace
some paths and invoke `gmake` on other platforms:

```bash
$ pwd
.../Krun
$ env JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64/ make  \
    JAVA_CPPFLAGS='"-I${JAVA_HOME}/include -I${JAVA_HOME}/include/linux"' \
    JAVA_LDFLAGS=-L${JAVA_HOME}/lib ENABLE_JAVA=1
```

## Step 4: Build the benchmarks

```bash
$ cd examples/benchmarks
$ pwd
.../krun/examples/benchmarks
$ make
```

If you also want to try the example Java benchmarks, you must build them
as a separate step:

```bash
$ pwd
.../krun/examples/benchmarks
$ make java-bench
```

## Step 5: Audit system services

You should take some time to review the services running on your benchmarking
machine. Debian especially has a habit of starting daemons which get pulled in
by dependencies.

Some services you can disable at boot. Others you may want disabled only for
the duration of the benchmarking (e.g. mail servers, crond, atd, ntpd). For the
latter kind, you can use `PRE_EXECUTION_CMDS` and `POST_EXECUTION_CMDS` in your
Krun config file to stop and start the services.

Note that by default Debian machines do not use a service like ntpd to set the
system time. Instead the time is set using `ntpdate` when a network interface
comes up.

### Linux

On Linux, list services with:

```
# systemctl | grep running
```

Disable services (now and at boot) with:

```
# systemctl stop <service>
# systemctl disable <service>
```

Commonly enabled services you probably don't want include:

 * apache2
 * memcached
 * nfs-common

### OpenBSD

On OpenBSD, list at services with:

```
# rcctl ls started
```

Disable services (now and at boot) with:
```
# rcctl stop <service>
# rcctl disable <service>
```

Commonly enabled services you probably don't want include:

 * pflogd
 * sndiod

## Step 6: Run the example experiment

```bash
$ cd ../
$ pwd
.../krun/examples
$ ../krun.py example.krun
```

You should see a log scroll past, and results will be stored in the file:
`../krun/examples/example_results.json.bz2`.

If you want to try the example Java benchmarks, there is a separate
configuration file called `java.krun`, which contains configuration for the Java
and Python examples:

```bash
$ pwd
.../krun/examples
$ ../krun.py java.krun

Note, this will only work if you have followed the extra steps above to
compile Krun for use with Java.

## Using a Krun results file

Krun generates a bzipped JSON file containing results of all process executions.
The structure of the JSON results is as follows:

```python
{
    'audit': '',  # A dict containing platform information
    'config': '', # A unicode object containing your Krun configuration
    'wallclock_times': {        # A dict object containing timing results
        'bmark:VM:variant': [   # A list of lists of in-process iteration times
            [ ... ], ...        # One list per process execution
        ]
    },
    'core_cycle_counts': {      # Per-core core cycle counter deltas
        'bmark:VM:variant': [
            [                   # One list per process execution
                [...], ...      # One list per core
            ]
    },
    'aperf_counts': {...}       # Per-core APERF deltas
                                # (structure same as 'core_cycle_counts')
    'mperf_counts': {...}       # Per-core MPERF deltas
                                # (structure same as 'core_cycle_counts')
    'eta_estimates': {u"bmark:VM:variant": [t_0, t_1, ...], ...} # A dict mapping
                  # benchmark keys to rough process execution times. Used internally,
                  # users can ignore this.
}
```

Some options exist to help inspect the results file:

  * `--dump-reboots`
  * `--dump-etas`
  * `--dump-config`
  * `--dump-audits`
  * `--dump-temps`
  * `--dump-data`

```bash
$ python krun.py --dump-config examples/example_results.json.bz2
INFO:root:Krun starting...
[2015-11-02 14:23:31: INFO] Krun starting...
import os
from krun.vm_defs import (PythonVMDef, NativeVMDef)
from krun import EntryPoint

# Who to mail
MAIL_TO = []
...

$ python krun.py --dump-audit examples/example_results.json.bz2
{
    "cpuinfo":  "processor\t: 0\nvendor_id\t: GenuineIntel\ncpu family\t:
...

$ python krun.py --dump-reboots examples/example_results.json.bz2
[2015-11-06 13:14:35: INFO] Krun starting...
8
```

## Testing your configurations

It is often useful to test a configuration file, without actually
running a full benchmark (especially if the benchmark program is
long). The best to test a config is to do something like:

```bash
$ ../krun.py --dry-run --quick --debug=INFO example.krun
```

See the "Development and Debug Switches" section for a description of these
switches.

Another switch, `--info`, reports various statistics about the setup described in the
specified config file, such as the total number of process executions and which
benchmark keys will be skipped etc.

## Creating your own experiments

The configuration file `examples/example.krun` controls the experiment here.
To create your own experiments, you can start by expanding on this example.
The directory structure for the

```
experiment/
    experiment.krun
    benchmarks/
        Makefile
        benchmark_1/
            language_1/
            benchmark_file.lang1
    ...
```

The `Makefile` (or similar build configuration) should perform any necessary
compilation or preprocessor steps.
Each benchmark should expose a function (or method) called `run_iter`
which is the entry point to the benchmark.
In the case of compiled languages, it often makes sense to add an extra
class to an existing benchmark, in order to provide an entry point.

The examples here uses C, Java and cPython.
The following VMs are currently supported:

  * Standard Java SDK (such as Hotspot)
  * GraalVM
  * cPython
  * Lua
  * PHP
  * Ruby
  * TruffleRuby
  * Javascript V8

To add a new VM definition, add a new class to `krun/vm_defs.py` and a
new iteration runner to the `iterations_runners` directory.

The following platforms are currently supported:

  * Generic Linux
  * Debian-based Linux

To add a new platform definition, add a new class to `krun/platform.py`.

## Development and Debug Switches

If you are making changes to Krun itself (for example, to add a new platform or
virtual machine definition), there are a few switches which can make your life
easier.

  * `--debug=<level>`: Sets the verbosity of Krun.  Valid debug levels are:
     `DEBUG`, `INFO`, `WARN`, `DEBUG`, `CRITICAL` and `ERROR`. The default is
     `WARN`. For real benchmarks you should use the default.

  * `--quick`: There are several places where Krun would normally wait using
    sleeps or a polling loop. These are essential for real benchmarking, but
    annoying for development. Use `--quick` to skip these delays.

  * `--no-user-change`: Without this flag, For each process execution, Krun
    will use a fresh user account called 'krun'. This involves deleting any
    existing user account (with `userdel -r`) and creating a new user account
    (with `useradd -m`).  This switch disables the use of a fresh user account,
    meaning that `userdel` and `useradd` are not invoked, nor does Krun switch
    user; the user Krun was invoked with is used for benchmarking.

  * `--dry-run`: Fakes actual benchmark processes, making them finish
    instantaneously.

  * `--no-tickless-check`: Do not crash out if the Linux kernel is not
    tickless.

  * `--no-pstate-check`: Do not crash out if Intel P-states are not disabled.

## Benchmarking for reliable results

You should not collect results intended for publication with development switches
turned on.

We also recommend that for 'real' benchmarking you turn on the
`--hardware-reboots` and `--daemonise` switches. These ensure that the system
will reboot before each benchmark execution, and that Krun will run in the
background, allowing you to log out before the first reboot.

You will also need to ensure that Krun is restarted once the machine has
rebooted. The `etc/` directory contains example `/etc/rc.local` files for the
platforms supported by Krun.

## Unit Tests

Krun has a pytest suite which can be run by executing `py.test` in the
top-level source directory.

## Security Notes

Krun is not intended to be run on a secure multi-user system, as it uses `sudo`
to elevate privileges. It also uses files with fixed names in `/tmp/` which means
that only one instance of Krun should be run at any one time (running more
than one leads to undefined behaviour).

`sudo` is used to:

 * Add and remove a fresh benchmarking user for each process execution.
 * Switch users.
 * Change the CPU speed.
 * Set the perf sample rate (Linux only)
 * Automatically reboot the system (`--hardware-reboots` only).
 * Set process priorities.
 * Create cgroup shields (Linux only, off by default)
 * Detect virtualised hosts.
 * Unrestrict the dmesg buffer (Linux Kernel 4.8+)
 * Turn off "turbo boost" (Linux only)

Please make sure you understand the implications of this.

## Licenses

Krun is licensed under the UPL license.

The nbody benchmark is licensed under a revised BSD license:
http://shootout.alioth.debian.org/license.php
