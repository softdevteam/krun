# Various CPU related abstrations

import time
import os
import difflib
import random
from collections import OrderedDict
from krun import ABS_TIME_FORMAT
from krun.util import fatal, run_shell_cmd, log_and_mail
from logging import warn, info, debug
from time import localtime

class BasePlatform(object):
    CPU_TEMP_MANDATORY_WAIT = 1
    CPU_TEMP_POLL_FREQ = 10                 # seconds between polls
    CPU_TEMP_POLLS_BEFORE_MELTDOWN = 60     # times 10 = ten mins

    def __init__(self, mailer):
        self.mailer = mailer
        self.audit = OrderedDict()

        # We will be looking for changes in the dmesg output.
        # In the past we have seen benchmarks trigger performance-related
        # errors and warnings in the Linux dmesg. If that happens, we
        # really want to know about it!
        self.last_dmesg = self._collect_dmesg_lines()
        self.last_dmesg_time = localtime()
        self.dmesg_changes = []

    def _collect_dmesg_lines(self):
        return run_shell_cmd("dmesg")[0].split("\n")

    def _timestamp_to_str(self, lt):
        return time.strftime(ABS_TIME_FORMAT, lt)

    def check_dmesg_for_changes(self):
        new_dmesg_time = localtime()
        new_dmesg = self._collect_dmesg_lines()

        old_fn = self._timestamp_to_str(self.last_dmesg_time)
        new_fn = self._timestamp_to_str(new_dmesg_time)
        lines = [x for x in difflib.unified_diff(
            self.last_dmesg, new_dmesg, old_fn, new_fn, lineterm="")]

        if lines:
            # dmesg changed!
            diff = "\n".join(lines)
            warn_s = "dmesg seems to have changed! Diff follows:\n" + diff
            log_and_mail(self.mailer, warn, "dmesg changed", warn_s)

            self.dmesg_changes.append(diff)
            self.last_dmesg = new_dmesg
            self.last_dmesg_time = new_dmesg_time

    def print_all_dmesg_changes(self):
        if not self.dmesg_changes:
            return

        warn_s = (
            "dmesg output changed during benchmarking!\n"
            "It is advisable to check for errors and warnings\n"
        )

        n_changes = len(self.dmesg_changes)
        for i in range(n_changes):
            warn_s += "dmesg change %d/%d:\n" % (i + 1, n_changes)
            warn_s += self.dmesg_changes[i] + "\n"

        warn(warn_s)

    def wait_until_cpu_cool(self):
        time.sleep(BasePlatform.CPU_TEMP_MANDATORY_WAIT)
        msg_shown = False
        trys = 0
        while True:
            debug("Temp poll %d/%d" %
                  (trys + 1, BasePlatform.CPU_TEMP_POLLS_BEFORE_MELTDOWN))
            cool, reason = self.has_cpu_cooled()
            if cool:
                break

            # if we get here, CPU is too hot!
            if not msg_shown:
                info("CPU is running hot.")
                info(reason)
                info("Waiting to cool")
                msg_shown = True

            trys += 1
            if trys >= BasePlatform.CPU_TEMP_POLLS_BEFORE_MELTDOWN:
                fatal("CPU didn't cool down")

            time.sleep(BasePlatform.CPU_TEMP_POLL_FREQ)

    # When porting to a new platform, implement the following:
    def take_cpu_temp_readings(self):
        raise NotImplementedError("abstract")

    def set_base_cpu_temps(self):
        raise NotImplementedError("abstract")

    def has_cpu_cooled(self):
        raise NotImplementedError("abstract")

    def check_preliminaries(self):
        raise NotImplementedError("abstract")

    # And you may want to extend this
    def collect_audit(self):
        self.audit["uname"] = run_shell_cmd("uname")[0]
        self.audit["dmesg"] = run_shell_cmd("dmesg")[0]

    # You may wish to override this if you need to prepend arguments to the
    # benchmark invocation, e.g. to use a tool to pin a benchmark to a CPU.
    def bench_cmdline_adjust(self, args):
        """Accepts a list representing the cmd line invocation of a benchmark.
        Returns a possibly mutated argument list."""
        return args  # default does nothing.

class LinuxPlatform(BasePlatform):
    """Deals with aspects generic to all Linux distributions. """

    THERMAL_BASE = "/sys/class/thermal/"
    CPU_GOV_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_governor"
    TURBO_DISABLED = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    ROOT_CMD = "sudo"
    CPU_SCALER_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_driver"
    KERNEL_ARGS_FILE = "/proc/cmdline"

    # We will wait until the CPU cools to within TEMP_THRESHOLD_PERCENT
    # percent warmer than where we started.
    TEMP_THRESHOLD_PERCENT = 10

    def __init__(self, mailer):
        self.base_cpu_temps = None
        self.temp_thresholds = None
        self.zones = self._find_thermal_zones()
        self.num_cpus = self._get_num_cpus()
        self.isolated_cpu = None  # Detected later
        BasePlatform.__init__(self, mailer)


    def bench_cmdline_adjust(self, args):
        """Adjusts benchmark invocation so as to pin to one CPU core"""

        # The core mask is a bitfield, each bit representing a CPU. When
        # a bit is set, it means the task may run on the corresponding core.
        # E.g. a mask of 0x3 (0b11) means the process can run on cores
        # 1 and 2. We want to pin the process to one CPU, so we only ever
        # set one bit.
        coremask = 1 << self.isolated_cpu
        return  ["taskset", hex(coremask)] + args

    def _find_thermal_zones(self):
        return [x for x in os.listdir(LinuxPlatform.THERMAL_BASE) if
                x.startswith("thermal_zone")]

    def _get_num_cpus(self):
        cmd = "cat /proc/cpuinfo | grep -e '^processor.*:' | wc -l"
        return int(run_shell_cmd(cmd)[0])

    def set_base_cpu_temps(self):
        self.base_cpu_temps = self.take_cpu_temp_readings()
        self.temp_thresholds = \
            [int(x + x * (1.0 / LinuxPlatform.TEMP_THRESHOLD_PERCENT))
             for x in self.base_cpu_temps]

    def _read_zone(self, zone):
        fn = os.path.join(LinuxPlatform.THERMAL_BASE, zone, "temp")
        with open(fn, "r") as fh:
            return int(fh.read())

    def take_cpu_temp_readings(self):
        return [self._read_zone(z) for z in self.zones]

    def has_cpu_cooled(self):
        """returns tuple: (bool_cool, str_reason_if_false)

        'bool_cool' is True if the CPU has cooled (or was never hot).

        'str_reason_if_false' is None if the CPU cooled down
        (bool_cool=True) , otherwise it is a string indicating the reason
        the CPU failed to cool.
        """

        assert self.base_cpu_temps is not None

        readings = self.take_cpu_temp_readings()
        debug("start temps: %s" % self.base_cpu_temps)
        debug("temp thresholds: %s" % self.temp_thresholds)
        debug("temp reading: %s" % readings)
        for i in range(len(self.temp_thresholds)):
            if readings[i] > self.temp_thresholds[i]:
                reason = ("Zone %d started at %d but is now %d. " \
                          "Needs to cool to within %d%% (%d)" % \
                          (i, self.base_cpu_temps[i],
                           readings[i], LinuxPlatform.TEMP_THRESHOLD_PERCENT,
                           self.temp_thresholds[i]))
                return (False, reason)  # one or more sensor too hot
        return (True, None)

    def save_power(self):
        """Called when benchmarking is done, to save power"""

        for cpu_n in xrange(self.num_cpus):
            debug("Set CPU%d governor to 'ondemand'" % cpu_n)
            cmd = "%s cpufreq-set -c %d -g ondemand" % \
                (self.ROOT_CMD, cpu_n)
            stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)

            if rc != 0:
                # Doesn't really matter if this fails, so just warn.
                warn("Could not set CPU%d governor to 'ondemand' when "
                     "finished.\nFailing command:\n%s" % (cpu_n, cmd))

    def check_preliminaries(self):
        """Checks the system is in a suitable state for benchmarking"""

        self._check_taskset_installed()
        self._check_cpu_isolated()
        self._check_cpu_governor()
        self._check_cpu_scaler()

    def _check_taskset_installed(self):
        from distutils.spawn import find_executable
        if not find_executable("taskset"):
            fatal("taskset not installed. Krun needs this to pin the benchmarks to an isolated CPU")

    def _check_cpu_isolated(self):
        """Attempts to detect an isolated CPU to run benchmarks on"""

        with open(LinuxPlatform.KERNEL_ARGS_FILE) as fh:
            all_args = fh.read().strip()

        args = all_args.split(" ")
        for arg in args:
            if '=' not in arg:
                continue

            k, v = arg.split("=", 1)

            if k != "isolcpus":
                continue
            else:
                if "," in v:
                    debug("Multiple isolated CPUs detected: %s" % v)
                    vs = v.split(",")
                    isol_cpu = int(random.choice(vs))
                    debug("Chose (at random) to isolate CPU %d" % isol_cpu)
                else:
                    isol_cpu = int(v)
                    debug("Detected sole isolated CPU %d" % isol_cpu)
                break
        else:
            fatal("Krun failed to detect an isolated CPU!\n"
                  "Did you add `isolcpus=X` to the kernel arguments?\n"
                  "To do this on Debian:\n"
                  "  * Edit /etc/default/grub\n"
                  "  * Add the argument to GRUB_CMDLINE_LINUX_DEFAULT\n"
                  "  * Run `sudo update-grub`\n"
                  "When the system comes up, check `ps -Pef`.")

        if isol_cpu == 0:
            fatal("Krun detected CPU 0 as the isolated CPU.\n"
                  "We reccommend using another CPU in case the first CPU "
                  "is ever special-cased in the kernel.")

        self.isolated_cpu = isol_cpu


    def _check_cpu_governor(self):
        """Checks the right CPU governor is in effect

        Since we do not know which CPU benchmarks will be scheduled on,
        we simply check them all"""

        # Check CPU cores are running with the 'performance' governor
        # And that the correct scaler is in use. We never want the pstate
        # scaler, as it tends to cause the clock speed to fluctuate, even
        # when in performance mode. Instead we use standard ACPI.
        for cpu_n in xrange(self.num_cpus):
            # Check CPU governors
            debug("Checking CPU governor for CPU%d" % cpu_n)
            with open(LinuxPlatform.CPU_GOV_FMT % cpu_n, "r") as fh:
                v = fh.read().strip()

            if v != "performance":
                cmd = "%s cpufreq-set -c %d -g performance" % \
                    (self.ROOT_CMD, cpu_n)
                stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)

                if rc != 0:
                    fatal("Governor for CPU%d governor: is '%s' not "
                          "performance'.\nKrun attempted to adjust the "
                          "governor using:\n  '%s'\n"
                          "however this command failed. Is %s configured "
                          "and is cpufrequtils installed?"
                          % (cpu_n, v, cmd, self.ROOT_CMD))

    def _check_cpu_scaler(self):
        """Check the correct CPU scaler is in effect"""

        for cpu_n in xrange(self.num_cpus):
            # Check CPU scaler
            debug("Checking CPU scaler for CPU%d" % cpu_n)
            with open(LinuxPlatform.CPU_SCALER_FMT % cpu_n, "r") as fh:
                v = fh.read().strip()

            if v != "acpi-cpufreq":
                if v == "intel_pstate":
                    scaler_files = [ "  * " + LinuxPlatform.CPU_SCALER_FMT % x for
                                    x in xrange(self.num_cpus)]
                    fatal("The kernel is 'intel_pstate' for scaling instead of 'acpi-cpufreq.\n"
                          "To use acpi-cpufreq, add 'intel_pstate=disable' to "
                          "the kernel arguments.\nOn debian:\n"
                          "  * Edit /etc/default/grub\n"
                          "  * Add the argument to GRUB_CMDLINE_LINUX_DEFAULT\n"
                          "  * Run `sudo update-grub`\n"
                          "When the system comes up, check the following "
                          "files contain 'acpi-cpufreq':\n%s"
                          % "\n".join(scaler_files))
                else:
                    fatal("The kernel is using '%s' for CPU scaling instead "
                          "of using 'acpi-cpufreq'" % v)

        # Check "turbo boost" is disabled
        # It really should be, as turbo boost is only available using pstates,
        # and the code above is ensuring we are not. Let's check anyway.
        debug("Checking 'turbo boost' is disabled")
        if os.path.exists(LinuxPlatform.TURBO_DISABLED):
            with open(LinuxPlatform.TURBO_DISABLED) as fh:
                v = int(fh.read().strip())

            if v != 1:
                fatal("Machine has 'turbo boost' enabled. "
                      "This should not happen, as this feature only applies to "
                      "pstate CPU scaling and Krun just determined that "
                      "the system is not!")


    def collect_audit(self):
        BasePlatform.collect_audit(self)

        # Extra CPU info, some not in dmesg. E.g. CPU cache size.
        self.audit["cpuinfo"] = run_shell_cmd("cat /proc/cpuinfo")[0]

class DebianLinuxPlatform(LinuxPlatform):
    def collect_audit(self):
        LinuxPlatform.collect_audit(self)
        self.audit["packages"] = run_shell_cmd("dpkg-query -l")[0]
        self.audit["debian_version"] = run_shell_cmd("cat /etc/debian_version")[0]

def platform(mailer):
    if os.path.exists("/etc/debian_version"):
        return DebianLinuxPlatform(mailer)
    else:
        fatal("I don't have support for your platform")
