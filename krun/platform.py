# Various CPU related abstrations

import time
import os
import difflib
import random
import sys
from collections import OrderedDict
from krun import ABS_TIME_FORMAT
from krun.util import fatal, run_shell_cmd, log_and_mail
from logging import warn, info, debug
from time import localtime
from abc import ABCMeta, abstractmethod, abstractproperty
from krun.env import EnvChangeSet

NICE_PRIORITY = -20
BENCHMARK_USER = "krun"  # user is expected to have made this
DIR = os.path.abspath(os.path.dirname(__file__))
LIBKRUNTIME_DIR = os.path.join(DIR, "..", "libkruntime")

class BasePlatform(object):
    __metaclass__ = ABCMeta

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
    @abstractproperty
    def CHANGE_USER_CMD(self):
        pass

    @abstractmethod
    def take_cpu_temp_readings(self):
        pass

    @abstractmethod
    def set_base_cpu_temps(self):
        pass

    @abstractmethod
    def has_cpu_cooled(self):
        pass

    @abstractmethod
    def check_preliminaries(self):
        pass

    @abstractmethod
    def unbuffer_fd(self, fd):
        pass

    @abstractmethod
    def adjust_env_cmd(self, env_dct):
        pass

    @abstractproperty
    def FORCE_LIBRARY_PATH_ENV_NAME(self):
        pass

    # And you may want to extend this
    def collect_audit(self):
        self.audit["uname"] = run_shell_cmd("uname")[0]
        self.audit["dmesg"] = run_shell_cmd("dmesg")[0]

    def bench_cmdline_adjust(self, args, env_dct):
        """Prepends various arguments to benchmark invocation.

        Currently deals with:
          * Changing user
          * CPU pinning (if available)
          * Adding libkruntime to linker path
          * Process priority"""

        # Force libkruntime into linker path.
        # We are working on the assumption that no-one else uses
        # LD_LIBRARY_PATH (or equivalent) elsewhere. EnvChangeSet will check
        # this and crash out if this assumption is invalid.
        combine_env = env_dct.copy()
        chng = EnvChangeSet(self.FORCE_LIBRARY_PATH_ENV_NAME, LIBKRUNTIME_DIR)
        chng.apply(combine_env)

        return self.change_user_args(BENCHMARK_USER) + \
            self.process_priority_args() + self.isolate_process_args() + \
            self.adjust_env_cmd(combine_env) + args

    @abstractmethod
    def change_user_args(self, user="root"):
        pass

    @abstractmethod
    def isolate_process_args(self):
        pass

    @abstractmethod
    def process_priority_args(self):
        pass

    @abstractmethod
    def get_reboot_cmd(self):
        pass


class UnixLikePlatform(BasePlatform):
    """A UNIX-like platform, e.g. Linux, BSD, Solaris"""

    FORCE_LIBRARY_PATH_ENV_NAME = "LD_LIBRARY_PATH"
    REBOOT = "reboot"

    def unbuffer_fd(self, fd):
        import fcntl
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fl |= os.O_SYNC
        fcntl.fcntl(fd, fcntl.F_SETFL, fl)

    def process_priority_args(self):
        return ["nice", str(NICE_PRIORITY)]

    def adjust_env_cmd(self, env_dct):
        """Construct a command prefix with env_dict set using env(1)"""

        args = ["env"]
        for t in env_dct.iteritems():
            args.append("%s=%s" % t)
        return args

    def change_user_args(self, user="root"):
        return [self.CHANGE_USER_CMD, "-u", user]


class OpenBSDPlatform(UnixLikePlatform):
    CHANGE_USER_CMD = "doas"

    def __init__(self, mailer):
        UnixLikePlatform.__init__(self, mailer)

    def get_reboot_cmd(self):
        cmd = self.change_user_args()
        cmd.append(self.REBOOT)
        return cmd

    def has_cpu_cooled(self):
        warn("CPU temperature checks not yet implemented on OpenBSD")
        return True, None  # XXX not implemented

    def check_preliminaries(self):
        warn("System preliminaries not yet implemented on OpenBSD")
        pass  # XXX not implemented

    def isolate_process_args(self):
        warn("CPU isolation not yet implemented on OpenBSD")
        return []  # XXX not implemented, not sure if possible

    def set_base_cpu_temps(self):
        warn("CPU temperature checks not yet implemented on OpenBSD")
        pass  # XXX not implemented

    def take_cpu_temp_readings(self):
        warn("CPU temperature checks not yet implemented on OpenBSD")
        return []  # XXX not implemeted

    @abstractmethod
    def save_power(self):
        pass

    def save_power(self):
        warn("power management support not implemented on OpenBSD")
        pass  # XXX not implemented


class LinuxPlatform(UnixLikePlatform):
    """Deals with aspects generic to all Linux distributions. """

    THERMAL_BASE = "/sys/class/thermal/"
    CPU_GOV_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_governor"
    TURBO_DISABLED = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    PERF_SAMPLE_RATE = "/proc/sys/kernel/perf_event_max_sample_rate"
    CHANGE_USER_CMD = "sudo"
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
        UnixLikePlatform.__init__(self, mailer)


    def _fatal_kernel_arg(self, arg, prefix, suffix):
        """Bail out and inform user how to add a kernel argument"""

        # This is generic Linux advice.
        # If you can offer better distribution-specific advice, override this
        # in a more specific Linux subclass.

        if prefix != "":
            prefix += "\n"

        if suffix != "":
            suffix += "\n"

        fatal("%s"
              "Set `%s` in the kernel arguments.\n"
              "%s" % (prefix, arg, suffix))

    def isolate_process_args(self):
        """Adjusts benchmark invocation to pin to a CPU core with taskset"""

        # The core mask is a bitfield, each bit representing a CPU. When
        # a bit is set, it means the task may run on the corresponding core.
        # E.g. a mask of 0x3 (0b11) means the process can run on cores
        # 1 and 2. We want to pin the process to one CPU, so we only ever
        # set one bit.
        coremask = 1 << self.isolated_cpu
        return ["taskset", hex(coremask)]

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
                (self.CHANGE_USER_CMD, cpu_n)
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
        self._check_perf_samplerate()
        self._check_tickless_kernel()

    @staticmethod
    def _tickless_config_info_str(modes):
        msg = ""
        for k, v in modes.iteritems():
            if v:
                yn = "y"
            else:
                yn = "n"
            msg += "%s=%s " % (k, yn)
        return msg

    @staticmethod
    def _open_kernel_config_file():
        """Open the kernel config file in /boot. Separated for mocking."""

        # get kernel release string, e.g. "3.16.0-4-amd64"
        stdout, _, _ = run_shell_cmd("uname -r")
        kern_rel_str = stdout.strip()

        config_basename = "config-%s" % kern_rel_str
        config_path = os.sep + os.path.join("boot", config_basename)

        return open(config_path, "r")

    def _check_tickless_kernel(self):
        """Check the Linux kernel was built for full tickless operation."""

        debug("Checking linux kernel is tickless")

        # These are the variables of interest. They are described well here:
        # http://lwn.net/Articles/549580/
        # and here:
        # https://www.kernel.org/doc/Documentation/timers/NO_HZ.txt
        modes = {
            # Scheduler ticks always occur. Rare in modern linux.
            "CONFIG_NO_HZ_PERIODIC": False,
            # Omit scheduler ticks when CPU is idle.
            "CONFIG_NO_HZ_IDLE": False,
            # Omit scheduler ticks when CPU has only one runnable process.
            # This is the one we want to see enabled.
            "CONFIG_NO_HZ_FULL": False,
        }

        # Walk kernel config looking for a lines describing tickless operation
        fh = LinuxPlatform._open_kernel_config_file()
        for line in fh:
            line = line.strip()
            if line == "" or line.startswith('#'):
                continue

            k, v = line.split("=")

            if k not in modes:
                continue

            if v not in ["y", "n"]:
                fatal("Unexpected value for kernel config key '%s': '%s'" % (k, v))

            if v == "y":
                modes[k] = True  # else it v was "n", and stays off

        fh.close()

        tickless_info_msg = LinuxPlatform._tickless_config_info_str(modes)

        # These settings should be mutually exclusive.
        enabled = [x for x in modes.itervalues() if x]
        if len(enabled) != 1:
            msg = "Tickless settings in kernel make no sense.\n"
            msg += tickless_info_msg + "\n"
            msg += "Only one of the three should be set."
            fatal(msg)


        if not modes["CONFIG_NO_HZ_FULL"]:
            msg = "Linux kernel is not tickless.\n"
            msg += tickless_info_msg + "\n"
            msg += "Please compile and boot a tickless kernel (CONFIG_HZ_FULL=y)"
            fatal(msg)

        debug(tickless_info_msg)

    def _check_perf_samplerate(self):
        """Attempt to minimise time spent by the Linux perf kernel profiler.
        You can't disable this, so the best we can do is set the sample
        rate to the minimum value of one sample per second."""

        with open(LinuxPlatform.PERF_SAMPLE_RATE) as fh:
            sr = int(fh.read().strip())

        if sr != 1:
            cmd = "%s sh -c 'echo 1 > %s'" % \
                (LinuxPlatform.CHANGE_USER_CMD, LinuxPlatform.PERF_SAMPLE_RATE)
            stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)

            if rc != 0:
                fatal("perf profiler sample rate >1 p/s. "
                      "Krun was unable to adjust it.\nFailing command:\n  %s"
                      % cmd)


    def _check_taskset_installed(self):
        from distutils.spawn import find_executable
        if not find_executable("taskset"):
            fatal("taskset not installed. Krun needs this to pin the benchmarks to an isolated CPU")

    def _check_cpu_isolated(self):
        """Attempts to detect an isolated CPU to run benchmarks on"""

        # XXX Isolating the CPU will not prevent kernel threads running.
        # We *may* be able to prevent atleast some kernel threads running,
        # but it seems cset (the facility to do this on Linux) is currently
        # broken on Debian (and perhaps elsewhere too). Bug filed at Debian:
        # http://www.mail-archive.com/debian-bugs-dist%40lists.debian.org/msg1349750.html

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
            self._fatal_kernel_arg(
                "isolcpus=X",
                "Krun failed to detect an isolated CPU!",
                "Choose X > 0. When the system comes up, check `ps -Pef`.")

        if isol_cpu == 0:
            self._fatal_kernel_arg(
                "isolcpus=X",
                "Krun detected CPU 0 as the isolated CPU.\n"
                "We reccommend using another CPU in case the first CPU "
                "is ever special-cased in the kernel.",
                "Choose X > 0")

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
                    (self.CHANGE_USER_CMD, cpu_n)
                stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)

                if rc != 0:
                    fatal("Governor for CPU%d governor: is '%s' not "
                          "performance'.\nKrun attempted to adjust the "
                          "governor using:\n  '%s'\n"
                          "however this command failed. Is %s configured "
                          "and is cpufrequtils installed?"
                          % (cpu_n, v, cmd, self.CHANGE_USER_CMD))

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
                    self._fatal_kernel_arg(
                        "intel_pstate=disable",
                        "The kernel is using 'intel_pstate' for scaling instead of 'acpi-cpufreq.",
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

    def get_reboot_cmd(self):
        cmd = self.change_user_args()
        cmd.append(self.REBOOT)
        return cmd


class DebianLinuxPlatform(LinuxPlatform):
    def collect_audit(self):
        LinuxPlatform.collect_audit(self)
        self.audit["packages"] = run_shell_cmd("dpkg-query -l")[0]
        self.audit["debian_version"] = run_shell_cmd("cat /etc/debian_version")[0]


    def _fatal_kernel_arg(self, arg, prefix="", suffix=""):
        """Debian specific advice on adding/changing a kernel arg"""

        if prefix != "":
            prefix += "\n"

        if suffix != "":
            suffix += "\n"

        fatal("%s"
              "Set `%s` in the kernel arguments.\n"
              "To do this on Debian:\n"
              "  * Edit /etc/default/grub\n"
              "  * Add the argument to GRUB_CMDLINE_LINUX_DEFAULT\n"
              "  * Run `sudo update-grub`\n"
              "%s" % (prefix, arg, suffix))


def detect_platform(mailer):
    plat_name = sys.platform
    if plat_name.startswith("linux"):
        if os.path.exists("/etc/debian_version"):
            return DebianLinuxPlatform(mailer)
        else:
            fatal("Unknown Linux platform")
    elif plat_name.startswith("openbsd"):
        return OpenBSDPlatform(mailer)
    else:
        fatal("I don't have support for your platform")
