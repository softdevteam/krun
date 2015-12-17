# Various platform related abstrations

import time
import os
import difflib
import random
import sys
from distutils.spawn import find_executable
from collections import OrderedDict
from krun import ABS_TIME_FORMAT
from krun.util import (fatal, run_shell_cmd, log_and_mail,
                       PLATFORM_SANITY_CHECK_DIR)
import krun.util as util
from logging import warn, info, debug
from time import localtime
from abc import ABCMeta, abstractmethod, abstractproperty
from krun.env import EnvChangeSet, EnvChange, EnvChangeAppend

NICE_PRIORITY = -20
DIR = os.path.abspath(os.path.dirname(__file__))
LIBKRUNTIME_DIR = os.path.join(DIR, "..", "libkruntime")


class BasePlatform(object):
    __metaclass__ = ABCMeta

    # We will wait until the zones cools to within TEMP_THRESHOLD_PERCENT
    # percent warmer than where we started.
    TEMP_THRESHOLD_PERCENT = 10

    TEMP_MANDATORY_WAIT = 1
    TEMP_POLL_FREQ = 10                 # seconds between polls
    TEMP_POLLS_BEFORE_MELTDOWN = 60     # times 10 = ten mins

    def __init__(self, mailer):
        self.developer_mode = False
        self.mailer = mailer
        self.audit = OrderedDict()

        # Temperatures should always be a dict mapping a descriptive name of
        # the sensor to a platform dependent linear temperature measurement.
        # The starting temperatures will be multiplied by a constant factor to
        # derive thresholds that characterise "too hot".
        self._starting_temperatures = {}  # accessed via property
        self.temperature_thresholds = {}

        self.last_dmesg = None
        self.last_dmesg_time = None

    def collect_starting_dmesg(self):
        # We will be looking for changes in the dmesg output.
        # In the past we have seen benchmarks trigger performance-related
        # errors and warnings in the Linux dmesg. If that happens, we
        # really want to know about it!
        self.last_dmesg = self._collect_dmesg_lines()
        self.last_dmesg_time = localtime()

    @property
    def starting_temperatures(self):
        return self._starting_temperatures

    @starting_temperatures.setter
    def starting_temperatures(self, readings_dct):
        """Sets the starting temperatures and automatically updates the
        temperature thresholds."""

        self._starting_temperatures = readings_dct
        for name, val in readings_dct.iteritems():
            self.temperature_thresholds[name] = \
                int(val + val * (1.0 / self.TEMP_THRESHOLD_PERCENT))

        debug("Setstart temperatures: %s" % readings_dct)
        debug("Temperatures thresholds: %s" % self.temperature_thresholds)

    def has_cooled(self):
        """Returns tuple: (bool_cool, str_reason_if_false)

        'bool_cool' is True if the system has cooled (or was never hot).

        'str_reason_if_false' is None if the system cooled down.
        (bool_cool=True) , otherwise it is a string indicating the reason
        the system failed to cool.
        """

        assert self._starting_temperatures != {}

        readings = self.take_temperature_readings()
        debug("start temperatures: %s" % self._starting_temperatures)
        debug("temp thresholds: %s" % self.temperature_thresholds)
        debug("temp reading: %s" % readings)

        for name, threshold in self.temperature_thresholds.iteritems():
            now_val = readings[name]
            start_val = self.starting_temperatures[name]
            if readings[name] > threshold:
                # This reading is too hot
                reason = ("Temperature reading '%s' started at %d but is now %d. " \
                          "Needs to cool to within %d%% (%d)" %
                          (name, start_val, now_val,
                           self.TEMP_THRESHOLD_PERCENT, threshold))
                return (False, reason)  # one or more sensor too hot
        return (True, None)

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

            self.last_dmesg = new_dmesg
            self.last_dmesg_time = new_dmesg_time

            return True  # i.e. a (potential) error occurred
        return False

    def wait_until_cool(self):
        if self.developer_mode:
            warn("Not waiting for cooling due to developer mode")
            return

        time.sleep(BasePlatform.TEMP_MANDATORY_WAIT)
        msg_shown = False
        trys = 0
        while True:
            debug("Temp poll %d/%d" %
                  (trys + 1, BasePlatform.TEMP_POLLS_BEFORE_MELTDOWN))
            cool, reason = self.has_cooled()
            if cool:
                break

            # if we get here, too hot!
            if not msg_shown:
                info("System is running hot.")
                info(reason)
                info("Waiting to cool")
                msg_shown = True

            trys += 1
            if trys >= BasePlatform.TEMP_POLLS_BEFORE_MELTDOWN:
                fatal("System didn't cool down")

            time.sleep(BasePlatform.TEMP_POLL_FREQ)

    # When porting to a new platform, implement the following:
    @abstractmethod
    def take_temperature_readings(self):
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
        self.audit["uname"] = run_shell_cmd("uname -a")[0]
        self.audit["dmesg"] = run_shell_cmd("dmesg")[0]

    def bench_cmdline_adjust(self, args, env_dct):
        """Prepends various arguments to benchmark invocation.

        Currently deals with:
          * CPU pinning (if available)
          * Adding libkruntime to linker path
          * Process priority

        It does not deal with changing user, as this is done one
        level up in the wrapper script."""

        # platform specific env changes to apply (if any)
        combine_env = env_dct.copy()
        changes = self.bench_env_changes()
        EnvChange.apply_all(changes, combine_env)

        return self.process_priority_args() + self.isolate_process_args() + \
            self.adjust_env_cmd(combine_env) + args

    @abstractmethod
    def _change_user_args(self, user="root"):
        pass

    def change_user_args(self, user="root"):
        if self.developer_mode:
            warn("Not switching user due to developer mode")
            return []
        else:
            return self._change_user_args(user)

    @abstractmethod
    def _isolate_process_args(self):
        pass

    def isolate_process_args(self):
        if self.developer_mode:
            warn("Not forcing onto isolated core due to developer mode")
            return []  # don't use isolated core at all
        else:
            return self._isolate_process_args()

    @abstractmethod
    def process_priority_args(self):
        pass

    @abstractmethod
    def get_reboot_cmd(self):
        pass

    def save_power(self):
        if self.developer_mode:
            warn("Not adjusting CPU governor due to developer mode")
            return
        else:
            debug("Save power")
            self._save_power()

    @abstractmethod
    def _save_power(self):
        pass

    @abstractmethod
    def bench_env_changes(self):
        pass

    @abstractmethod
    def sanity_checks(self):
        pass


class UnixLikePlatform(BasePlatform):
    """A UNIX-like platform, e.g. Linux, BSD, Solaris"""

    FORCE_LIBRARY_PATH_ENV_NAME = "LD_LIBRARY_PATH"
    REBOOT = "reboot"

    def __init__(self, mailer):
        self.change_user_cmd = find_executable("sudo")
        if self.change_user_cmd is None:
            fatal("Could not find sudo!")

        BasePlatform.__init__(self, mailer)

    def bench_env_changes(self):
        # Force libkruntime into linker path.
        # We are working on the assumption that no-one else uses
        # LD_LIBRARY_PATH (or equivalent) elsewhere. EnvChangeSet will check
        # this and crash out if this assumption is invalid.
        return [EnvChangeAppend(self.FORCE_LIBRARY_PATH_ENV_NAME,
                                LIBKRUNTIME_DIR)]

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

    def _change_user_args(self, user="root"):
        return [self.change_user_cmd, "-u", user]

    def sanity_checks(self):
        self._sanity_check_user_change()

    def _sanity_check_user_change(self):
        from krun.vm_defs import PythonVMDef
        from krun import EntryPoint

        ep = EntryPoint("check_user_change.py")
        vd = PythonVMDef(sys.executable)  # run under the VM that runs *this*
        util.spawn_sanity_check(self, ep, vd, "UNIX user change",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)


class OpenBSDPlatform(UnixLikePlatform):
    TEMP_SENSORS_CMD = "sysctl -a | grep -e 'hw\.sensors\..*\.temp'"
    GET_SETPERF_CMD = "sysctl hw.setperf"

    # flags to set OpenBSD MALLOC_OPTIONS to. We disable anything that could
    # possibly introduce non-determinism.
    # 's' first acts to reset free page cache to default.
    # See malloc.conf(5) and src/lib/libc/stdlib/malloc.c for more info.
    MALLOC_OPTS = "sfghjpru"

    def __init__(self, mailer):
        self.temperature_sensors = []
        UnixLikePlatform.__init__(self, mailer)

    def bench_env_changes(self):
        # Force malloc flags
        changes = UnixLikePlatform.bench_env_changes(self)
        changes.append(EnvChangeSet("MALLOC_OPTIONS", self.MALLOC_OPTS))
        return changes

    def get_reboot_cmd(self):
        cmd = self.change_user_args()
        cmd.append(self.REBOOT)
        return cmd

    def check_preliminaries(self):
        self._check_apm_state()

    def _get_apm_output(self):
        # separate for mocking
        return run_shell_cmd("apm")[0]

    def _check_apm_state(self):
        info("Checking APM state is geared for high-performance")
        adjust = False

        out = self._get_apm_output()
        lines = out.split("\n")

        n_lines = len(lines)
        if n_lines != 3:
            fatal("Expected 3 lines of output from apm(8), got %d" % n_lines)

        perf_line = lines[2].strip()

        # First, the performance mode should be manual (static)
        if not perf_line.startswith("Performance adjustment mode: manual"):
            debug("performance mode is not manual.")
            adjust = True

        # Second, the CPU should be running as fast as possible
        out, _, _ = run_shell_cmd(self.GET_SETPERF_CMD)
        elems = out.split("=")
        if len(elems) != 2 or elems[1].strip() != "100":
            debug("hw.setperf is '%s' not '100'" % elems[1])
            adjust = True

        if adjust:
            info("adjusting performance mode")
            out, _, _ = run_shell_cmd("apm -H")
            self._check_apm_state()  # should work this time

    def _isolate_process_args(self):
        # We cannot isolate CPUs on OpenBSD
        return []

    def _get_sysctl_temperature_output(self):
        # separate for test mocking
        return run_shell_cmd(self.TEMP_SENSORS_CMD)[0]

    def take_temperature_readings(self):
        lines = self._get_sysctl_temperature_output()
        readings = {}
        for line in lines.split("\n"):
            elems = line.split("=")

            if len(elems) != 2:
                fatal("Malformed sensor sysctl line: '%s'" % line)

            k, v = elems
            v_elems = [x.strip() for x in v.split(" ")]
            k = k.strip()

            # Typically the value element looks like:
            # "49.00 degC" or "48.00 degC (zone temperature)"
            # We will only concern ourself with the first two elements.
            if len(v_elems) < 2 or v_elems[1] != "degC":
                fatal("sensor '%s' has an odd non-degC value: '%s'" % (k, v))

            try:
                temp_val = float(v_elems[0])
            except ValueError:
                fatal("sensor '%s' has a non-numeric value: '%s'" % (k, v_elems[0]))

            readings[k] = temp_val

        return readings

    def _save_power(self):
        run_shell_cmd("apm -C")

    def sanity_checks(self):
        UnixLikePlatform.sanity_checks(self)
        self._malloc_options_sanity_check()

    def _malloc_options_sanity_check(self):
        """Checks MALLOC_OPTIONS are set"""

        from krun import EntryPoint
        ep = EntryPoint("check_openbsd_malloc_options")

        from krun.vm_defs import NativeCodeVMDef, SANITY_CHECK_HEAP_KB
        vd = NativeCodeVMDef()

        util.spawn_sanity_check(self, ep, vd, "OpenBSD malloc options",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)


class LinuxPlatform(UnixLikePlatform):
    """Deals with aspects generic to all Linux distributions. """

    THERMAL_BASE = "/sys/class/thermal/"
    CPU_GOV_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_governor"
    TURBO_DISABLED = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    PERF_SAMPLE_RATE = "/proc/sys/kernel/perf_event_max_sample_rate"
    CPU_SCALER_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_driver"
    KERNEL_ARGS_FILE = "/proc/cmdline"
    ASLR_FILE = "/proc/sys/kernel/randomize_va_space"

    def __init__(self, mailer):
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

    def _isolate_process_args(self):
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

    def _read_zone(self, zone):
        fn = os.path.join(LinuxPlatform.THERMAL_BASE, zone, "temp")
        with open(fn, "r") as fh:
            return int(fh.read())

    def take_temperature_readings(self):
        return dict([(z, self._read_zone(z)) for z in self.zones])

    def _save_power(self):
        """Called when benchmarking is done, to save power"""

        for cpu_n in xrange(self.num_cpus):
            debug("Set CPU%d governor to 'ondemand'" % cpu_n)
            cmd = "%s cpufreq-set -c %d -g ondemand" % \
                (self.change_user_cmd, cpu_n)
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
        self._check_aslr_disabled()

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
                (LinuxPlatform.change_user_cmd, LinuxPlatform.PERF_SAMPLE_RATE)
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
        changed = False
        for cpu_n in xrange(self.num_cpus):
            # Check CPU governors
            debug("Checking CPU governor for CPU%d" % cpu_n)
            with open(LinuxPlatform.CPU_GOV_FMT % cpu_n, "r") as fh:
                v = fh.read().strip()

            if v != "performance":
                info("changing CPU governor for CPU %s" % cpu_n)
                cmd = "%s cpufreq-set -c %d -g performance" % \
                    (self.change_user_cmd, cpu_n)
                stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)
                changed = True

                if rc != 0:
                    fatal("Governor for CPU%d governor: is '%s' not "
                          "performance'.\nKrun attempted to adjust the "
                          "governor using:\n  '%s'\n"
                          "however this command failed. Is %s configured "
                          "and is cpufrequtils installed?"
                          % (cpu_n, v, cmd, self.change_user_cmd))
        if changed:
            self._check_cpu_governor()  # just to be sure

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

    def _check_aslr_disabled(self):
        debug("Checking ASLR is off")
        with open(self.ASLR_FILE, "r") as fh:
                enabled = fh.read().strip()
        if enabled == "0":
            return  # OK!
        else:
            # ASLR is off, but we can try to enable it
            info("Turning ASLR off")
            cmd = "%s sh -c 'echo 0 > %s'" % \
                (self.change_user_cmd, self.ASLR_FILE)
            stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)

            if rc != 0:
                msg = "ASLR disabled (%s, expect '0' got '%s').\n" % \
                    (self.ASLR_FILE, enabled)
                msg += "Krun tried to turn it off, but failed."
                fatal(msg)
            else:
                self._check_aslr_disabled()  # should work this time

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
