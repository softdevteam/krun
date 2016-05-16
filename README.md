# Krun

Krun is a framework for running software benchmarking experiments.

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

You need to have the following installed:

  * Python2.7 (pre-installed in Debian)
  * GNU make, a C compiler and libc (`build-essential` package in Debian)
  * cpufrequtils (Linux only. `cpufrequtils` package in Debian)
  * cffi (`python-cffi` package in Debian)
  * cset (for pinning on Linux only. `cpuset` package in Debian)

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

### Create a user called krun

You will need to create a new user called `krun`, with minimal permissions:

```bash
sudo useradd krun
```

You will want to add this user to the `sudoers` group and make sure that
the user does not need a password for `sudo` as root.

## Step 2: Fetch the Krun source

```bash
$ git clone https://github.com/softdevteam/krun.git
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

## Step 5: Run the example experiment

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
    'data': {     # A dict object containing timing results
        u'bmark:VM:variant': [  # A list of lists of in-process iteration times
            [ ... ], ...        # One list per process execution
        ]
    },
    'reboots': N, # An int containing the number of reboots that have
                  # already taken place. Only used when Krun is started
                  # with --reboot. This field used to check that the
                  # benchmarking machine has rebooted the correct number
                  # of times. It can be safely ignored by users.
    'starting_temperatures': [ ... ], # Temperatures recorded at the beginning
                  # of the experiment. Used before each process execution to decide if
                  # the system is running much hotter than before. In this
                  # case we wait to allow the system to cool. The ordering
                  # and meanings of the temperatures in the list are platform
                  # and system specific. This information can be safely
                  # ignored by users.
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

This directory (`examples/`) contains two Python scripts which show
how to consume results in Krun format:

  * `results2csv.py` which converts the results data to `.csv` files
  * `chart_results.py` which shows a number of interactive charts

`results2csv.py` only requires the Python standard library.
`chart_results.py` requires maptplotlib and statsmodels v0.6 or higher.


## Testing your configurations

It is often useful to test a configuration file, without actually
running a full benchmark (especially if the benchmark program is
long).
Krun supports this with the `--dryrun` command line switch:

```bash
$ ../krun.py --dryrun --debug=INFO example.krun
```

By passing in `--debug=INFO` you will see a full log of krun actions
printed to STDOUT.
Valid debug levels are: `DEBUG`, `INFO`, `WARN`, `DEBUG`,
`CRITICAL`, `ERROR`.

The `--info` switch reports various statistics about the setup described in the
specified config file, such as the total number of process executions and which
benchmark keys will be skipped etc.

## Running in reboot and resume modes

Krun can resume an interrupted benchmark by passing in the `--resume`
flag.
This will read and re-use results from previous process executions of your
benchmarks, and run the remaining process executions detailed in your configuration
file.

```bash
$ ../krun.py --resume example.krun
```

You may wish to use this facility to reboot after every process execution.
To do this, you can pass in the `--reboot` flag when you start Krun:

```bash
$ ../krun.py --reboot example.krun
```

You will also need to ensure that Krun is restarted once the machine has
rebooted.
You can do this by hand, or by using the boot configuration provided by
your OS.
A boot configuration file should pass in the `--reboot`, `--resume` and
`started-by-init` flags to Krun.
This will suppress some emails that Krun sends out.

The `krun/etc` directory contains an `rc.local.linux` file which goes
with the examples here.
This file is compatible with some Linux machines.

### Testing a benchmark run with `--reboot`

If you need to test a benchmark configuration with `--reboot`, you can
still use the `--dryrun` flag.
In a dry run, Krun will not reboot your machine (it will simulate
rebooting by restarting Krun automatically) and will not pause to
wait for your network interface to come up.

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
  * JRuby
  * Truffle-JRuby
  * Javascript V8

To add a new VM definition, add a new class to `krun/vm_defs.py` and a
new iteration runner to the `iterations_runners` directory.

The following platforms are currently supported:

  * Generic Linux
  * Debian-based Linux

To add a new platform definition, add a new class to `krun/platform.py`.

## Developer Mode

If you are making changes to Krun itself (for example, to add a new platform or
virtual machine definition), you may find the `--develop` switch useful. This
will cause Krun to run with the following modifications:

  * Krun will not run the system prerequisite checks. Checks relating to CPU
    governors,  CPU scalers, CPU temperatures, tickless kernel, etc.
  * Krun will not attempt to switch user to run benchmarks.

This makes it easier to develop krun on (e.g.) a personal laptop which has not
been prepared for reliable benchmarking.

Note that you should not collect results intended for publication with
`--develop`.

## Re-running Part of your Experiment

Sometimes it is necessary to re-run a subset of your experiment. For example,
if after completing an experiment, you find that one of your VMs was
miscompiled, you may want to re-run all benchmarks for the troublesome VM only.
Of course, under ideal circumstances, you would collect all results in one go.

You can use the `--strip-results` mode to strip results from your result file.
Once stripped, you can run with `--resume` to re-collect the results you
stripped.

The switch accepts a "key-spec". All process executions matching the key-spec
are removed. A key-spec is of the form 'benchmark:vm:variant". Any of the three
fields can also be a star '*' to indicate a wildcard. E.g. `--strip-results
'*:CPython:*'` will remove all results for the 'CPython' VM. If ou use a
wildcard, be sure to quote the argument so the shell does not expand the stars.

Note also that the stars are not true wildcards. E.g. the key-spec '*:CPy*:*'
will not match 'mybenchmark:CPython:myvariant'. Fields are either a value or
literally '*'.

Once you have stripped results, if you ran an experiment in reboot mode you
will need to reboot manually to re-run the stripped results (with rc.local set
up correctly).

## Licenses

The *nbody* benchmark comes from the Computer Language Benchmarks Game, which
are published under a revised BSD license:

  http://shootout.alioth.debian.org/license.php
