# krun example

This directory contains a simple experiment using krun.
This is a good starting point for setting up your own krun configuration.

The example here contains two benchmark programs (*nbody* and *dummy*),
executed on two VMs (*cPython* and a standard *JVM* such as HotSpot).
Each benchmark is run for 5 iterations on the same VM, then the VM is
restarted and the benchmark is re-run for another 5 iterations.
We say that the experiment runs 2 *executions* and 5 *iterations* of
each benchmark.

This configuration can be found in the file `examples/example.krun`.

## Step 1: prepare the benchmarking machine

krun currently only runs on Unix-like environments.
To run this example experiment, you need superuser rights to the machine you are
using, e.g. on Linux you should be able to run `sudo`.

You need to have the following installed:

  * Python
  * a Java SDK (version 7)
  * GNU make, a C compiler and libc (e.g. `sudo apt-get install build-essential`)
  * cpufrequtils (e.g. `sudo apt-get install cpufrequtils`)
  * cffi (e.g. `sudo apt-get install python-cffi`)

If you are using a Linux system, you will need to set some kernel arguments.
If your Linux bootloader is Grub, you can follow these steps:

  * Edit /etc/default/grub (e.g. `sudo gedit /etc/default/grub`)
  * Add `isolcpus=X` to `GRUB_CMDLINE_LINUX_DEFAULT` (where `X` is an integer > 0)
  * Add `intel_pstate=disable` to `GRUB_CMDLINE_LINUX_DEFAULT`
  * Run `sudo update-grub`

Create a new user called `krun`, with minimal permissions:

```bash
sudo useradd krun
```

## Step 2: Fetch the krun source

```bash
$ git clone https://github.com/softdevteam/krun.git
$ cd krun
```

## Step 3: set `JAVA_HOME`

```bash
$ export JAVA_HOME=/usr/lib/jvm/java-7-openjdk-amd64/
```
## Step 4: Build krun

The krun Makefile honours the standard variables: `CC`, `CPPFLAGS`, `CFLAGS`
and `LDFLAGS`. For example, if you wish to use `clang` rather than `gcc` you
can append `CC=/bin/clang` to the options here:

```bash
$ pwd
.../krun
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