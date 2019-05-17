# Krun

Krun is a framework for running high-quality software benchmarking experiments.
Krun experiments consist of a configuration file, a carefully configured
benchmarking machine, and the benchmarks themselves.


## Step 1: Initial installation

Krun currently only runs on Debian Linux and OpenBSD. Porting it to other
Unix variants is unlikely to be difficult, and we welcome patches.

### Dependencies

You need to have the following programs installed:

  * sudo
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
  * policykit (Linux only, only if you want to use `systemctl start/stop` in
    `PRE/POST_EXECUTION_CMDS`. See *Benchmarking for Reliable Results* below)

If you want to benchmark Java, you will also need:

  * A Java SDK (`openjdk-*-jdk` package in Debian).


## Step 2 (Linux only): kernel and OS setup

### P-states

Benchmarking is at its most accurate when Intel p-states are disabled in
the kernel. If you are using Grub, this can be achieved as follows:

  * Edit `/etc/default/grub` so that the `GRUB_CMDLINE_LINUX_DEFAULT`
    variable includes `intel_pstate=disable`.
  * Run `sudo update-grub`

If you are unable to do this, you can disable Krun's P-state check with
`--disable-pstate-check`, but be aware that this degrades the quality of the
resulting benchmarking numbers.

### Performance counters

We recommend using our custom Linux kernel found at:

  https://github.com/softdevteam/krun-linux-kernel

which provides low latency access to the following counters:

  * `IA32_PERF_FIXED_CTR1` (the core cycle counter)
  * `IA32_APERF` counts
  * `IA32_MPERF` counts

If you are unable to do this, you can set `NO_MSRS=1` in your Unix environment
when building Krun (see later), but be aware that this degrades the quality of
the resulting benchmarking numbers.

Krun works on any version of the kernel if NO_MSRS=1 is set. If a suitable
version of the Krun custom kernel (>= 4.9.88) is used, the MSRs are also
available.

## Step 3: Fetch and build Krun

First fetch Krun:

```sh
$ git clone --recursive https://github.com/softdevteam/krun.git
$ cd krun
```

Then run `make` (or `gmake` on OpenBSD). The Krun Makefile honours the standard
variables: `CC`, `CPPFLAGS`, `CFLAGS` and `LDFLAGS`.

If you want to benchmark Java programs, you need to set the
`JAVA_HOME` environment variable to point to your JDK installation, and
set several other flags:

```sh
$ JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64/ make  \
    JAVA_CPPFLAGS='"-I${JAVA_HOME}/include -I${JAVA_HOME}/include/linux"' \
    JAVA_LDFLAGS=-L${JAVA_HOME}/lib ENABLE_JAVA=1
```


## Step 4: Audit system services

Background services (e.g. `cron` or `sendmail`) can interfere with benchmarking.
The more services that you are able to switch off, the less interference is
likely to occur. Some services are best disabled at boot and/or permanently
(depending on your OS) and must be done manually. However, you may wish
to disable some services only during benchmarking (e.g. you may wish to have a mail server
running before and after benchmarking to inform you of benchmarking progress),
which can be specified in the `PRE_EXECUTION_CMDS` and `POST_EXECUTION_CMDS`
settings in your Krun config file.

Commands in each list are run, in order, using the `krun` user's shell (e.g.
`/bin/sh`). If a command fails, Krun stops execution immediately without running
subsequent commands. If you wish execution to continue even if a command fails
you can use standard shell idioms: e.g. `cmd || true` guarantees that the
overall command succeeds even if `cmd` fails. 

For example on a systemd Linux you may turn daemons off before execution with:

```
PRE_EXECUTION_CMDS = [
    "sudo systemctl stop cron",
    "sudo systemctl stop atd",
    ...
]
```

and turn them back on with:

```
POST_EXECUTION_CMDS = [
    "sudo systemctl start cron || true",
    "sudo systemctl start atd || true",
    ...
]
```

In general it is best practise to turn things back on explicitly, because after
Krun runs the final benchmark it will not reboot the machine. If, for example,
you put network interfaces down in `PRE_EXECUTION_CMDS`, you should put them
back up in `POST_EXECUTION_CMDS` so that you can login to the machine after the
final benchmark has been run. We urge you to check such commands carefully:
small oversights can easily lead to you locking yourself out of the system.

Krun can also copy intermediate results to a remote host and query that host to
see whether it should suspend benchmarking. See
`https://github.com/softdevteam/warmup_experiment/blob/master/warmup.krun` for
more advanced options.


### Linux

Note that Debian has, from a benchmarking perspective, the unfortunate habit of
automatically starting daemons which get pulled in by dependencies.

On Linux, list services with:

```sh
# systemctl | grep running
```

Permanently disable services (including after system reset) with:

```sh
# systemctl stop <service>
# systemctl disable <service>
```

Commonly enabled services that you may wish to disable:

 * apache2
 * memcached
 * nfs-common


### OpenBSD

On OpenBSD, list services with:

```sh
# doas rcctl ls started
```

Permanently disable services (including after system reset) with:
```sh
# rcctl stop <service>
# rcctl disable <service>
```

Commonly enabled services that you may wish to disable:

 * pflogd
 * sndiod

Note that Krun is unable to check whether turbo mode is enabled on OpenBSD or
not, and is also unable to use APERF/MPERF ratios to indirectly check whether
turbo mode was used. You should therefore be particularly careful to check that
turbo mode is disabled when benchmarking on OpenBSD.


## Step 5: Build and run the example

The `examples` directory contains the `example.krun` experiment. This contains
two benchmark programs (*nbody* and *dummy*), both of which are run on *C* and
*PyPy*. Each benchmark is run for 5 *in-process iterations* (where the
benchmark is repeated 5 times within a for loop within a single process) across
2 *process executions* (where the entire VM is restarted).

First build the examples:

```sh
$ cd examples/benchmarks
$ pwd
.../krun/examples/benchmarks
$ make
```

If you also want to try the example Java benchmarks, you must build them
as a separate step:

```sh
$ pwd
.../krun/examples/benchmarks
$ make java-bench
```

Then run the example:

```sh
$ cd krun/examples
$ ../krun.py example.krun
```

You should see a log scroll past, and results will be stored in the file:
`../krun/examples/example_results.json.bz2`.

If you want to try the example Java benchmarks, there is a separate
configuration file called `java.krun`, which contains configuration for the Java
and Python examples:

```sh
$ ../krun.py java.krun
```

Note, this will only work if you have followed the earlier steps to compile
Krun with Java support.


### The Krun user

Krun runs benchmarks under a new Unix user `krun`, which is wiped and re-added
before every experiment. Your Krun build and your experiment must both be
readable by the `krun` user for the experiment to run.


## Creating your own experiments

It is easiest to use `examples/example.krun` as a template for your own,
new, experiments. Note that: the benchmarks referenced in the config file
*must* be in a `benchmarks` subdirectory; and that each benchmark in
the config must be in a subsubdirectory with a matching name. A typical
directory structure is therefore as follows:

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

The top-level `Makefile` should build the VMs and benchmarks needed for the
experiment.

Each benchmark should expose a function (or method) called `run_iter` which is
the entry point to the benchmark. To preserve source code history, it can
be easiest to put this function in a new file, which then imports the benchmark.

With regards to VM/compiler support, there are two ways Krun can invoke a
benchmark:

  * Via a dedicated "VM definition" (e.g. `JavaVMDef`).
  * Via an external benchmark suite (`ExternalSuiteVMDef`).

The former option is best, as it supports Krun's core-cycle counting and
APERF/MPERF ratio features. The following compilers/VMs are currently supported
for this mode:

  * Native code languages (`NativeCodeVMDef`).
  * OpenJDK. (i.e. Hotspot) (`JavaVMDef`).
  * GraalVM (`GraalVMDef`).
  * cPython (`PythonVMDef`).
  * Lua (`LuaVMDef`).
  * PHP (`PHPVMDef`).
  * Ruby (`RubyVMDef`).
  * TruffleRuby (`TruffleRubyVMDef`).
  * Javascript V8 (`V8VMDef`).

If your VM isn't listed, you can either add it to Krun, or use the external
suite definition (see below). To add a new VM definition, add a new class to
`krun/vm_defs.py` and a new iteration runner to the `iterations_runners`
directory.

The latter option -- `ExternalSuiteVMDef` -- is useful if you want to quickly
wrap an existing benchmark suite. For an example see `examples/ext.krun` and
`examples/ext_script.py`.

To add a new platform definition, add a new class to `krun/platform.py`.

## Testing your configurations

Before doing a full run of an experiment, you should perform a quick(ish) test
of your configuration. This can be achieved with:

```sh
$ /path/to/krun/krun.py --dry-run --quick --debug=INFO config.krun
```

See the "Development and Debug Switches" section for a description of these
switches.


## Production benchmarking

Achieving the highest possible benchmarking quality requires more care. First,
none of Krun's debug or development switches must be used. Second, Krun needs to
run in "reboot mode" where each process execution will be run after the machine
has (automatically) rebooted. The simplest way to do this is to have your init
system invoke `scripts/run_krun_at_boot` via an `rc.local` script.

Your `/etc/rc.local` should look like this:
```
#!/bin/sh
/usr/bin/sudo -u someuser /path/to/krun/scripts/run_krun_at_boot /path/to/your/config.krun
exit 0
```

Make sure you replace the paths as appropriate and substitute `someuser` with
the name of a normal unprivileged user that you wish to use to kick off Krun.

Make sure `/etc/rc.local` is executable and that it only contains absolute
paths. Note that `sudo(8)` is installed in different places on different
operating systems (for OpenBSD, it's `/usr/local/bin/sudo`).

Any arguments supplied after the config file path are passed to Krun unchanged.

You can then start the experiment by manually running the command from your new
`rc.local` (i.e. `sudo -u ...`).


### Monitoring progress

Whilst benchmarking is occuring, you must not log in to the machine (indeed,
hopefully `sshd`, or equivalent, has been disabled!). To monitor progress, and
be informed of errors, you you should add a `MAIL_TO` list of emails to your
Krun config file:

```python
MAIL_TO = ["me@mydomain.com", "other_person@herdomain.com"]
```

Krun uses `sendmail(8)` to send email, so you will need to make sure that
you have a functional SMTP server installed (and don't forget to switch it off
during benchmarking!).


## Custom Dmesg Whitelists

For each platform, Krun has a default built-in dmesg whitelist. The whitelist
is a collection of regex patterns which are used to decide if a line in the
dmesg buffer is a cause for concern. If a new line appears in the dmesg during
benchmarking, and the line is not matched by at least one whitelist pattern,
then Krun will flag the process execution as ``errored'' and email the user.

From time to time you may find that you need to customise the whitelist. This
is achieved by adding a callback named `custom_dmesg_whitelist` into your
config file. The callback is passed the default list of patterns for your
platform and must return a new list of patterns. In the implementation of your
callback you have the choice to base your custom whitelist on the defaults or
to define your own patterns from scratch.

For example, to add a pattern, you would add a callback like:

```python
def custom_dmesg_whitelist(defaults):
    return defaults + ["^.*your+regex.*pattern$"]
```

Krun uses Python's `re` module to compile regex patterns. Consult the Python
docs for more information on the regex syntax.

Bear in mind that Linux dmesg lines start with a time code which custom dmesg
lines will need to match.

If you have added custom patterns which you think would be useful for other
users of Krun, please raise an issue (or pull request) to have the patterns
added to the defaults.


## Development and Debug Switches

If you are making changes to Krun itself (for example, to add a new platform or
virtual machine definition), there are a few switches which can make your life
easier.

  * `--debug=<level>`: Sets the verbosity of Krun.  Valid debug levels are:
     `DEBUG`, `INFO`, `WARN`, `DEBUG`, `CRITICAL` and `ERROR`. The default is
     `WARN`. Production quality benchmarking should use the default.

  * `--quick`: There are several places where Krun pauses to allow the system
    to stabilise. In testing these pauses can be burdensome and can thus
    be skipped with `--quick`.

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


## Krun results files

Krun generates a bzipped JSON file containing results of all process executions.
The structure of the JSON results is as follows:

```python
{
    'audit': '',  # A dict containing platform information
    'config': '', # A unicode object containing your Krun configuration
    'wallclock_times': {        # A dict containing timing results
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
                  # benchmark keys to rough process execution times. Used internally:
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

```sh
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
 * Turn off memory over-commit (Linux only).

Please make sure you understand the implications of this.


## Licenses

Krun is licensed under the UPL license.

The nbody benchmark is licensed under a revised BSD license:
http://shootout.alioth.debian.org/license.php
