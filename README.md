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

Krun runs Linux systems (running a 3.x kernel) and OpenBSD.

You need to have the following installed:

  * Python2.7 (pre-installed in Debian)
  * GNU make, a C compiler and libc (`build-essential` package in Debian)
  * cpufrequtils (Linux only. `cpufrequtils` package in Debian)
  * cffi (`python-cffi` package in Debian)
  * cset (for pinning on Linux only. `cpuset` package in Debian)
  * virt-what (Linux only. `virt-what` package in Debian)
  * Linux kernel headers (Linux only. linux-headers-3... in Debian)

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

### Tickless Mode Linux Kernel

The Linux kernel can run in ``tickless'' configurations, where under certain
conditions regular tick interrupts can be avoided for a subset of logical CPUs.
More info here:
https://www.kernel.org/doc/Documentation/timers/NO_HZ.txt

On a Linux system, Krun will insist that the kernel is running in
"full tickless" mode with the NO_HZ_FULL_ALL compile time flag. This will place
all logical CPUs apart from the boot processor (i.e. CPU 0) into adaptive ticks
mode. If this is not enabled, you will need to build a custom kernel. You can
verify the tickless mode of the current kernel with:

```
cat /boot/config-`uname -r` | grep HZ
```

`CONFIG_NO_HZ_FULL_ALL` should be set to *y*. Krun will check this before
running benchmarks. It will also check this setting was not overridden on the
kernel command line with a `nohz_full=` argument. Please do not use this.

#### Building a Tickless Kernel

On a Debian machine, the easiest way to build a tickless kernel is to build
installable deb packages. This process is described
[here](https://debian-handbook.info/browse/stable/sect.kernel-compilation.html).

When you run `make menuconfig` to configure the kernel:

 * Go into `General
setup->Timers subsystem->Timer tick handling` and choose `Full dynticks system
(tickless)` (internally known as `CONFIG_NO_HZ_FULL`).

 * Then go up one level and select `Full dynticks system on all CPUs by default (except CPU 0)` (internally `NO_HZ_FULL_ALL`).

I also find it useful to give the kernel some useful name so that you can
identify it on a running system. To do this, in `make menuconfig` find `General
setup->Local Version` and type in a meaningful name. As tempting as it is, *do
not* use symbols in this name, as it will cause the Debian package build to
bomb out. I used `softdevnohzfullall`.

You can then continue to build and package as usual with `make deb-pkg`. Once
finished, you will find `.deb` files in the parent directory. To install them,
use `dpkg install`. This will automatically set the new kernel as the default
boot kernel. Reboot the system and check the kernel is running:

```
$ uname -r
3.16.7-ckt11softdevnohzfullall
$ cat /boot/config-`uname -r` | grep NO_HZ_FULL_ALL
CONFIG_NO_HZ_FULL_ALL=y
```

For more information on tickless mode, see
[the kernel docs](https://www.kernel.org/doc/Documentation/timers/NO_HZ.txt).

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
    exising user account (with `userdel -r`) and creating a new user account
    (with `useradd -m`).  This switch disables the use of a fresh user account,
    meaning that `userdel` and `useradd` are not invoked, nor does Krun switch
    user; the user Krun was invoked with is used for benchmarking.

  * `--dry-run`: Fakes actual benchmark processes, making them finish
    instantaneously.

  * `--no-tickless-check`: Do not crash out if the Linux kernel is not
    tickless.

  * `--no-pstate-check`: Do not crash out if Intel P-states are not disabled.

  * `--hardware-reboots`: Restart physical hardware before each benchmark
    execution.

Note that you should not collect results intended for publication with
development switches turned on.

## Unit Tests

Krun has a pytest suite which can be run by executing `py.test` in the
top-level source directory. The user running the tests should be in the `root`
group so as to allow access to `/dev/cpu/*/rmsr`.

## Security Notes

Krun is not intended to be run on a secure multi-user system, as it uses sudo
to elevate privileges.

Sudo is used to:

 * Add and remove a fresh benchmarking user for each process execution.
 * Switch users.
 * Change the CPU speed.
 * Set the perf sample rate (Linux only)
 * Automatically reboot the system (`--hardware-reboots` only).
 * Set process priorities.
 * Create cgroup shields (Linux only, off by default)
 * Detect virtualised hosts.
 * Change Linux capabilities(7) for MSR device node access.
 * Change MSR device node filesystem permissions.

Please make sure you understand the implications of this.

## Licenses

The *nbody* benchmark comes from the Computer Language Benchmarks Game, which
are published under a revised BSD license:

  http://shootout.alioth.debian.org/license.php
