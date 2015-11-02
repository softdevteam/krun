# Krun example

This directory contains a simple experiment using Krun.
This is a good starting point for setting up your own Krun configuration.

The example here contains two benchmark programs (*nbody* and *dummy*),
executed on two VMs (*cPython* and a standard *JVM* such as HotSpot).
Each benchmark is run for 5 iterations on the same VM, then the VM is
restarted and the benchmark is re-run for another 5 iterations.
We say that the experiment runs 2 *executions* and 5 *iterations* of
each benchmark.

This configuration can be found in the file `examples/example.krun`.

## Step 1: prepare the benchmarking machine

Krun currently only runs on Unix-like environments.
To run this example experiment, you need superuser rights to the machine you are
using, e.g. on Linux you should be able to run `sudo`.

### Dependencies

You need to have the following installed:

  * Python2.7 (other versions of Python are not supported)
  * a Java SDK (version 7)
  * GNU make, a C compiler and libc (e.g. `sudo apt-get install build-essential`)
  * cpufrequtils (e.g. `sudo apt-get install cpufrequtils`)
  * cffi (e.g. `sudo apt-get install python-cffi`)

### Kernel arguments

If you are using a Linux system, you will need to set some kernel arguments.
If your Linux bootloader is Grub, you can follow these steps:

  * Edit /etc/default/grub (e.g. `sudo gedit /etc/default/grub`)
  * Add `isolcpus=X` to `GRUB_CMDLINE_LINUX_DEFAULT` (where `X` is an integer > 0)
  * Add `intel_pstate=disable` to `GRUB_CMDLINE_LINUX_DEFAULT`
  * Run `sudo update-grub`

Also for a Linux system, Krun will insist that the kernel is running in
"tickless" mode.  Tickless mode is a compile time kernel parameter, so if it is
not enabled, you will need to build a custom kernel.  You can verify the
tickless mode of the current kernel with:

```
cat /boot/config-`uname -r` | grep HZ
```

`CONFIG_NO_HZ_FULL` should be set to *y*. Krun will check this before
running benchmarks.

On a Debian machine, the easiest way to build a tickless kernel is to build
installable deb packages. This process is described
[here](https://debian-handbook.info/browse/stable/sect.kernel-compilation.html).
When you run `make menuconfig` to configure the kernel, go into `General
setup->Timers subsystem->Timer tick handling` and choose `Full dynticks system
(tickless)`. You can then continue to build and package as usual. Once
finished, you will find `.deb` files in the parent directory. To install them,
use `dpkg install`.  This will automatically set the new kernel as the default
boot kernel.

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

## Step 3: set `JAVA_HOME`

```bash
$ export JAVA_HOME=/usr/lib/jvm/java-7-openjdk-amd64/
```
## Step 4: Build Krun

The Krun Makefile honours the standard variables: `CC`, `CPPFLAGS`, `CFLAGS`
and `LDFLAGS`. For example, if you wish to use `clang` rather than `gcc` you
can append `CC=/bin/clang` to the options here:

```bash
$ pwd
.../Krun
$ make JAVA_CPPFLAGS='"-I${JAVA_HOME}/include -I${JAVA_HOME}/include/linux"' \
    JAVA_LDFLAGS=-L${JAVA_HOME}/lib ENABLE_JAVA=1
```

## Step 5: Build the benchmarks

```bash
$ cd examples/benchmarks
$ pwd
.../krun/examples/benchmarks
$ make
```

## Step 6: Run the example experiment

```bash
$ cd ../
$ pwd
.../krun/examples
$ PYTHONPATH=../ ../krun.py example.krun
```

You should see a log scroll past, and results will be stored in the file:
`../krun/examples/example_results.json.bz2`.

## Using a Krun results file

Krun generates a bzipped JSON file containing results of all executions.
The structure of the JSON results is as follows:

```python
{
    'audit': '',  # A unicode object containing platform information
    'config': '', # A unicode object containing your Krun configuration
    'data': {     # A dict object containing timing results
        u'bmark:VM:variant': [  # A list of lists of timing results
            [ ... ], ...        # One list per execution
        ]
  }
}
```

Often it is useful to check the audit or configuration that a result
file was generated with.
To do this, call Krun with the `--dump-audit` or `--dump-config` options:

```bash
$ python krun.py --dump-config examples/example_results.json.bz2
INFO:root:Krun starting...
[2015-11-02 14:23:31: INFO] Krun starting...
import os
from krun.vm_defs import (PythonVMDef, JavaVMDef)
from krun import EntryPoint

# Who to mail
MAIL_TO = []
...

$ python krun.py --dump-audit examples/example_results.json.bz2
{
    "cpuinfo":  "processor\t: 0\nvendor_id\t: GenuineIntel\ncpu family\t:
...
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
$ PYTHONPATH=../ ../krun.py --dryrun --debug=INFO example.krun
```

By passing in `--debug=INFO` you will see a full log of krun actions
printed to STDOUT.
Valid debug levels are: `DEBUG`, `INFO`, `WARN`, `DEBUG`,
`CRITICAL`, `ERROR`.

## Running in reboot and resume modes

Krun can resume an interrupted benchmark by passing in the `--resume`
flag.
This will read and re-use results from previous executions of your
benchmarks, and run the remaining executions detailed in your configuration
file.

```bash
$ PYTHONPATH=../ ../krun.py --resume example.krun
```

You may wish to use this facility to reboot after every execution.
To do this, you can pass in the `--reboot` flag when you start Krun:

```bash
$ PYTHONPATH=../ ../krun.py --reboot example.krun
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

The example here uses Java and cPython.
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

## Licenses

The *nbody* benchmark comes from the Computer Language Benchmarks Game, which
are published under a revised BSD license:

  http://shootout.alioth.debian.org/license.php
