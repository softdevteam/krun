# Various platform related abstractions

import time
import os
import difflib
import random
import sys
import glob
import subprocess
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
LIBKRUNTIME_DIR = os.path.join(DIR, "..", "libkrun")


class BasePlatform(object):
    __metaclass__ = ABCMeta

    TEMP_THRESHOLD_DEGREES = 3
    TEMP_WAIT_SECS_BEFORE_GIVEUP = 60 * 60

    TEMP_OK = 0
    TEMP_TOO_HOT = 1
    TEMP_TOO_COLD = 2

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
        self.find_temperature_sensors()

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

        # Check consistency of sensors
        keys1 = list(sorted(readings_dct.keys()))
        keys2 = list(sorted(self.temp_sensors))
        if keys1 != keys2:
            fatal("Inconsistent sensors. %s vs %s" % \
                  (keys1, keys2))  # sensors moved between reboot?

        self._starting_temperatures = readings_dct
        debug("Set start temperatures: %s" % readings_dct)

    def temp_sensors_within_interval(self):
        """Indicates if all temperature sensors are close (within an interval)
        to their start readings.

        Returns tuple: (bool_ok, str_reason_if_false)

        'flag' is BasePlatform.TEMP_OK if all temperature sensors are within
        range, or BasePlatform.TEMP_TOO_HOT or BasePlatform.TEMP_TOO_COLD
        otherwise.

        'str_reason' is None if 'flag' is BasePlatform.TEMP_OK, otherwise it is
        a string message indicating the reason the system is not within the
        desired temperature range.
        """

        readings = self.take_temperature_readings()
        debug("start temperatures: %s" % self._starting_temperatures)
        debug("temp reading: %s" % readings)

        for name, now_val in readings.iteritems():
            start_val = self.starting_temperatures[name]
            low = start_val - self.TEMP_THRESHOLD_DEGREES
            high = start_val + self.TEMP_THRESHOLD_DEGREES

            if not (low <= now_val <= high):
                # This reading is too hot/cold
                reason = ("Temperature reading '%s' not within interval: "
                          "(%d <= %d <= %d)" % (name, low, now_val, high))

                if now_val < low:
                    flag = BasePlatform.TEMP_TOO_COLD
                else:
                    assert now_val > high
                    flag = BasePlatform.TEMP_TOO_HOT

                return (flag, reason)  # one or more sensor too hot or cold
        return (self.TEMP_OK, None)

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

    def wait_for_temperature_sensors(self, testing=False):
        """A polling loop waiting for temperature sensors to return (close) to
        their starting values.

        When 'testing' is True, only one iteration of the wait loop will
        run (used only in unit tests)."""

        if self.developer_mode:
            warn("Not waiting for temperature sensors due to developer mode")
            return

        if not testing:
            bail_out_time = time.clock() + self.TEMP_WAIT_SECS_BEFORE_GIVEUP
        else:
            bail_out_time = 0  # force only one iteration

        while True:
            flag, reason = self.temp_sensors_within_interval()

            if flag == self.TEMP_OK:
                break
            elif flag == self.TEMP_TOO_HOT:
                time.sleep(1)
            elif flag == self.TEMP_TOO_COLD:
                # This takes a variable amount of time, but on a modern
                # machine it takes only a fraction of a second.
                util.make_heat()

            if time.clock() >= bail_out_time:
                break

        if flag != self.TEMP_OK:
            fatal("Temperature timeout: %s" % reason)

    # When porting to a new platform, implement the following:
    @abstractmethod
    def take_temperature_readings(self):
        """Takes temperature readings in degrees centigrade"""
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

    @abstractmethod
    def sync_disks(self):
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

        It does not deal with changing user, as this is done one
        level up in the wrapper script."""

        # platform specific env changes to apply (if any)
        combine_env = env_dct.copy()
        changes = self.bench_env_changes()
        EnvChange.apply_all(changes, combine_env)

        return self.adjust_env_cmd(combine_env) + \
            self.pin_process_args() + args

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

    @abstractmethod
    def find_temperature_sensors(self):
        """Fill self.temp_sensors"""
        pass

    @abstractmethod
    def pin_process_args(self):
        pass


class UnixLikePlatform(BasePlatform):
    """A UNIX-like platform, e.g. Linux, BSD, Solaris"""

    FORCE_LIBRARY_PATH_ENV_NAME = "LD_LIBRARY_PATH"
    REBOOT = "reboot"
    NICE_CMD = "/usr/bin/nice"

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
        return [self.NICE_CMD, "-n", str(NICE_PRIORITY)]

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
        self._sanity_check_nice_priority()

    def _sanity_check_user_change(self):
        from krun.vm_defs import PythonVMDef
        from krun import EntryPoint

        ep = EntryPoint("check_user_change.py")
        vd = PythonVMDef(sys.executable)  # run under the VM that runs *this*
        util.spawn_sanity_check(self, ep, vd, "UNIX user change",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def _sanity_check_nice_priority(self):
        from krun.vm_defs import NativeCodeVMDef
        from krun import EntryPoint

        ep = EntryPoint("check_nice_priority.so")
        vd = NativeCodeVMDef()
        util.spawn_sanity_check(self, ep, vd, "Process priority",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def sync_disks(self):
        """Force pending I/O to physical disks"""

        debug("sync disks...")
        rc = subprocess.call("/bin/sync")
        if rc != 0:
            fatal("sync failed")

        # The OpenBSD manual says: "sync() [the system call] may return before
        # the buffers are completely flushed.", and the sync command is merely
        # a thin wrapper around the syscall. We wait a while. We have reports
        # that the sync command itself can take up to 10 seconds.
        time.sleep(30)


class OpenBSDPlatform(UnixLikePlatform):
    FIND_TEMP_SENSORS_CMD = "sysctl -a | grep -e 'hw\.sensors\..*\.temp'"
    GET_SETPERF_CMD = "sysctl hw.setperf"

    # flags to set OpenBSD MALLOC_OPTIONS to. We disable anything that could
    # possibly introduce non-determinism.
    # 's' first acts to reset free page cache to default.
    # See malloc.conf(5) and src/lib/libc/stdlib/malloc.c for more info.
    MALLOC_OPTS = "sfghjpru"

    def __init__(self, mailer):
        UnixLikePlatform.__init__(self, mailer)

    def find_temperature_sensors(self):
        lines = self._get_sysctl_sensor_lines()
        sensors = []
        for line in lines.split("\n"):
            elems = line.split("=")

            if len(elems) != 2:
                fatal("Malformed sysctl line: '%s'" % line)

            sensors.append(elems[0].strip())
        self.temp_sensors = sensors

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
        debug("Checking APM state is geared for high-performance")
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
            debug("adjusting performance mode")
            out, _, _ = run_shell_cmd("apm -H")
            self._check_apm_state()  # should work this time

    def _get_sysctl_sensor_lines(self):
        # separate for test mocking
        return run_shell_cmd(self.FIND_TEMP_SENSORS_CMD)[0]

    def _raw_read_temperature_sensor(self, sensor):
        # mocked in tests

        # sysctl doesn't return 0 on failure.
        # Luckily we can catch the error later when when the output
        # looks weird.
        return run_shell_cmd("sysctl %s" % sensor)[0]

    def take_temperature_readings(self):
        readings = {}
        for sensor in self.temp_sensors:
            line = self._raw_read_temperature_sensor(sensor)

            elems = line.split("=")

            if len(elems) != 2:
                fatal("Failed to read sensor: '%s'. "
                      "Malformed sysctl output: %s" % (sensor, line))

            k, v = elems
            v_elems = [x.strip() for x in v.split(" ")]
            k = k.strip()
            assert k == sensor

            # Typically the value element looks like:
            # "49.00 degC" or "48.00 degC (zone temperature)"
            # We will only concern ourself with the first two elements.
            # Notice that the values are already reported in degrees
            # centigrade, so we don't have to process them.
            if len(v_elems) < 2 or v_elems[1] != "degC":
                fatal("Failed to read sensor: '%s'. "
                      "Odd non-degC value: '%s'" % (k, v))

            try:
                temp_val = float(v_elems[0])
            except ValueError:
                fatal("Failed to read sensor %s. "
                      "Non-numeric value: '%s'" % (k, v_elems[0]))

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
        ep = EntryPoint("check_openbsd_malloc_options.so")

        from krun.vm_defs import NativeCodeVMDef, SANITY_CHECK_HEAP_KB
        vd = NativeCodeVMDef()

        util.spawn_sanity_check(self, ep, vd, "OpenBSD malloc options",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def pin_process_args(self):
        return []  # not supported on OpenBSD


class LinuxPlatform(UnixLikePlatform):
    """Deals with aspects generic to all Linux distributions. """

    HWMON_CHIPS_GLOB = "/sys/class/hwmon/hwmon[0-9]"
    CPU_GOV_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_governor"
    TURBO_DISABLED = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    PERF_SAMPLE_RATE = "/proc/sys/kernel/perf_event_max_sample_rate"
    CPU_SCALER_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_driver"
    KERNEL_ARGS_FILE = "/proc/cmdline"
    ASLR_FILE = "/proc/sys/kernel/randomize_va_space"

    # Expected tickless kernel config
    #
    # Futher info:
    #   http://lwn.net/Articles/549580/
    #   https://www.kernel.org/doc/Documentation/timers/NO_HZ.txt
    EXPECT_TICKLESS_CONFIG = {
        # Scheduler ticks always occur. Rare in modern linux.
        "CONFIG_NO_HZ_PERIODIC": False,

        # Omit scheduler ticks when CPU is idle.
        "CONFIG_NO_HZ_IDLE": False,

        # Omit scheduler ticks when an adaptive tick CPU has only one
        # runnable process. This enbles the tickless functionality, but the
        # system admin must manually specify on adaptive-tick CPUs via
        # the kernel command line. By default, no CPUs are adaptive tick,
        # so we insist also upon CONFIG_NO_HZ_FULL_ALL.
        "CONFIG_NO_HZ_FULL": True,

        # Same as CONFIG_NO_HZ_FULL, but forces all CPUs apart from the
        # boot CPU into adaptive tick mode. This is what we want to
        # see enabled. Note that you cannot have all CPUs in adaptive-tick.
        "CONFIG_NO_HZ_FULL_ALL": True,
    }

    def __init__(self, mailer):
        self.temp_sensor_map = None
        UnixLikePlatform.__init__(self, mailer)
        self.num_cpus = self._get_num_cpus()


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

    def find_temperature_sensors(self):
        """Detect sensors using the hwmon sysfs framework

        The sensors move between reboots, so we have to roll our own sensor
        identifier. We are not fussy, and use as many sensors as we can find."""

        # maps our identifier to actual sysfs filename
        sensor_map = {}

        hwmons = glob.glob(LinuxPlatform.HWMON_CHIPS_GLOB)
        for chip in hwmons:
            name_path = os.path.join(chip, "name")
            with open(name_path) as fh:
                chip_name = fh.read().strip()

            inputs_glob = os.path.join(chip, "temp[0-9]*_input")
            chip_sensors = glob.glob(inputs_glob)

            for sensor in chip_sensors:
                key = "%s:%s" % (chip_name, os.path.basename(sensor))
                assert key not in sensor_map  # two chips with the same name?
                sensor_map[key] = sensor

        debug("Detected temperature sensors: %s" % sensor_map)
        self.temp_sensors = sensor_map.keys()
        self.temp_sensor_map = sensor_map

    def _get_num_cpus(self):
        err = False

        # most reliable method generic to all Linux
        out, _, rv = run_shell_cmd("grep -c ^processor  /proc/cpuinfo")
        if rv == 0:
            out = out.strip()
            try:
                return int(out)
            except ValueError:
                pass

        fatal("could not detect number of logical CPUs")

    def _read_temperature_sensor(self, sid):
        try:
            sysfs_file = self.temp_sensor_map[sid]
        except KeyError:
            fatal("Failed to read sensor: %s (missing key)" % sid)

        try:
            with open(sysfs_file) as fh:
                return int(fh.read())
        except IOError:
            fatal("Failed to read sensor: %s at %s" % (sid, sysfs_file))

    def take_temperature_readings(self):
        # Linux thermal zones are reported in millidegrees celsius
        # https://www.kernel.org/doc/Documentation/thermal/sysfs-api.txt
        return {z: self._read_temperature_sensor(z) / 1000.0
                for z in self.temp_sensors}

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

    def _get_kernel_cmdline(self):
        with open(self.KERNEL_ARGS_FILE, "r") as fh:
            cmdline = fh.read().strip()
        return cmdline

    def _check_tickless_kernel(self):
        """Check the Linux kernel was built for full tickless operation."""

        debug("Checking linux kernel is tickless")

        # Start with all keys mapping to False
        modes = {k: False for k in self.EXPECT_TICKLESS_CONFIG.iterkeys()}

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

        if modes != self.EXPECT_TICKLESS_CONFIG:
            msg = "Linux kernel tickless settings are not as expected.\n"
            msg += "Did you install a tickless kernel?\n"
            msg += "Expect: %s\n" % self.EXPECT_TICKLESS_CONFIG
            msg += "Got: %s\n" % modes
            fatal(msg)

        # Finally, check the adaptive tick CPUs were not overrideen
        cmdline = self._get_kernel_cmdline()
        if "nohz_full" in cmdline:
            msg = "Adaptive-ticks CPUs overridden on kernel command line:\n"
            msg += "%s\n" % cmdline
            msg += "Please remove 'nohz_full' from the kernel command line"
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
                (self.change_user_cmd, LinuxPlatform.PERF_SAMPLE_RATE)
            stdout, stderr, rc = run_shell_cmd(cmd, failure_fatal=False)

            if rc != 0:
                fatal("perf profiler sample rate >1 p/s. "
                      "Krun was unable to adjust it.\nFailing command:\n  %s"
                      % cmd)

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
                debug("changing CPU governor for CPU %s" % cpu_n)
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
            debug("Turning ASLR off")
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

    def pin_process_args(self):
        """Pin to a set of adaptive tick CPUs.
        We are working the assumption that the kernel is NO_HZ_FULL_ALL meaning
        that all but the first CPU are in adaptive tick mode."""

        if self.num_cpus == 1:
            fatal("not enough CPUs to pin")

        cpus = ",".join([str(x) for x in xrange(1, self.num_cpus)])
        return ["taskset", "-c", cpus]

    def _check_taskset_installed(self):
        from distutils.spawn import find_executable
        if not find_executable("taskset"):
            fatal("taskset not installed (needed for pinning).")

    def sanity_checks(self):
        UnixLikePlatform.sanity_checks(self)
        self._check_taskset_installed()
        self._check_isolcpus()
        self._sanity_check_cpu_affinity()

    def _sanity_check_cpu_affinity(self):
        from krun.vm_defs import NativeCodeVMDef
        from krun import EntryPoint

        ep = EntryPoint("check_linux_cpu_affinity.so")
        vd = NativeCodeVMDef()
        util.spawn_sanity_check(self, ep, vd, "CPU affinity",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def _advise_isolcpus_arg(self, got_cpus, expect_cpus):
        """Error out and guide user in isolating CPUs"""

        arg = "isolcpus=%s" % ",".join(expect_cpus)
        self._fatal_kernel_arg(
            arg, "CPUs incorrectly isolated. Got: %s, expect: %s" %
            (got_cpus, expect_cpus)
        )

    def _check_isolcpus(self):
        """Checks the correct CPUs have been isolated.
        (All but the boot processor)"""

        expect_cpus = [str(x) for x in xrange(1, self.num_cpus)]
        all_args = self._get_kernel_cmdline()

        args = all_args.split(" ")
        for arg in args:
            if "=" not in arg:
                continue

            k, v = arg.split("=", 1)

            if k != "isolcpus":
                continue

            break  # found the isolcpus arg
        else:
            self._advise_isolcpus_arg([], expect_cpus)  # exits

        got_cpus = list(sorted(v.split(",")))

        if expect_cpus != got_cpus:
            self._advise_isolcpus_arg(got_cpus, expect_cpus)  # exits


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
              "  * Amend GRUB_CMDLINE_LINUX_DEFAULT\n"
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
