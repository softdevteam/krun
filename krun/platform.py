# Copyright (c) 2017 King's College London
# created by the Software Development Team <http://soft-dev.org/>
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or
# data (collectively the "Software"), free of charge and under any and all
# copyright rights in the Software, and any and all patent rights owned or
# freely licensable by each licensor hereunder covering either (i) the
# unmodified Software as contributed to or provided by such licensor, or (ii)
# the Larger Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
# one is included with the Software (each a "Larger Work" to which the Software
# is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright
# notice and either this complete permission notice or at a minimum a reference
# to the UPL must be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Various platform related abstractions

import time
import os
import difflib
import sys
import glob
import subprocess
import re
import pwd
import cffi
from distutils.spawn import find_executable
from collections import OrderedDict
from krun import ABS_TIME_FORMAT
from krun.util import (fatal, run_shell_cmd, log_and_mail,
                       PLATFORM_SANITY_CHECK_DIR)
import krun.util as util
from logging import warn, debug, info
from abc import ABCMeta, abstractmethod, abstractproperty
from krun.env import EnvChangeSet, EnvChange, EnvChangeAppend
from krun.vm_defs import BENCHMARK_USER

NICE_PRIORITY = -20
DIR = os.path.abspath(os.path.dirname(__file__))
LIBKRUNTIME_DIR = os.path.join(DIR, "..", "libkrun")
UTILS_DIR = os.path.join(DIR, "..", "utils")
SYNC_SLEEP_SECS = 30  # time to wait for sync() to finish


class BasePlatform(object):
    __metaclass__ = ABCMeta

    TEMP_THRESHOLD_DEGREES = 3
    TEMP_WAIT_SECS_BEFORE_GIVEUP = 60 * 60

    TEMP_OK = 0
    TEMP_TOO_HOT = 1
    TEMP_TOO_COLD = 2

    def __init__(self, mailer, config):
        self.quick_mode = False
        self.no_user_change = False
        self.no_pstate_check = False
        self.no_tickless_check = False
        self.hardware_reboots = False
        self.mailer = mailer
        self.audit = OrderedDict()
        self.config = config
        self.num_per_core_measurements = self._libkrun_num_cores()

        # Temperatures should always be a dict mapping a descriptive name of
        # the sensor to a platform dependent linear temperature measurement.
        # The starting temperatures will be multiplied by a constant factor to
        # derive thresholds that characterise "too hot".
        self._starting_temperatures = {}  # accessed via property
        self.temperature_thresholds = {}
        self.find_temperature_sensors()
        if self.get_num_temperature_sensors() == 0 and not self.is_virtual():
            fatal("No usable temperature sensors!")

        self.last_dmesg = None

    def _libkrun_num_cores(self):
        """Ask libkrun how many per-core readings we are expecting"""

        ffi = cffi.FFI()
        ffi.cdef("""
            void krun_init(void);
            void krun_done(void);
            uint64_t krun_get_num_cores(void);
        """)
        libkruntime = ffi.dlopen(os.path.join(LIBKRUNTIME_DIR, "libkruntime.so"))

        libkruntime.krun_init()
        n_cores = libkruntime.krun_get_num_cores()
        libkruntime.krun_done()

        debug("libkrun is working with %d cores for per-core counters" % n_cores)
        return n_cores

    def sleep(self, secs):
        if self.quick_mode:
            warn("SIMULATED: `time.sleep(%s)` (--quick)" % secs)
        else:
            time.sleep(secs)

    def collect_starting_dmesg(self):
        # We will be looking for changes in the dmesg output.
        # In the past we have seen benchmarks trigger performance-related
        # errors and warnings in the Linux dmesg. If that happens, we
        # really want to know about it!
        self.last_dmesg = self._collect_dmesg_lines()

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

    @abstractmethod
    def default_dmesg_whitelist(self):
        pass

    def get_dmesg_whitelist(self):
        default_whitelist = self.default_dmesg_whitelist()
        if self.config.custom_dmesg_whitelist is not None:
            # Invoke the user's custom function
            patterns = self.config.custom_dmesg_whitelist(default_whitelist)
        else:
            patterns = default_whitelist
        return [re.compile(p) for p in patterns]

    def filter_new_dmesg_line(self, line, patterns):
        for p in patterns:
            if p.match(line):
                debug("Allowed dmesg change: '%s'" % line)
                return True  # allowed change of dmesg
        return False

    def check_dmesg_for_changes(self, manifest):
        new_dmesg = self._collect_dmesg_lines()
        patterns = self.get_dmesg_whitelist()

        rv = self._check_dmesg_for_changes(patterns, self.last_dmesg,
                                           new_dmesg, manifest)
        self.last_dmesg = new_dmesg

        return rv

    def _check_dmesg_for_changes(self, patterns, last_dmesg, new_dmesg,
                                 manifest):
        differ = difflib.Differ()
        delta = list(differ.compare(last_dmesg, new_dmesg))
        delta_len = len(delta)
        new_lines = []
        dmesg_buffer_full = False

        # Lines (or, more likely, partial lines) can fall off the top of the
        # dmesg ring-buffer. We shouldn't report this as a change, so we first
        # consume delta lines that appear to have been caused by this. So we
        # effectively start diffing on the first common line present in both of
        # the dmesgs. Note that sometimes difflib flags a partial line with a
        # '? ' code, but it doesn't always get it right. We therefore don't
        # rely on this.
        for line_no in xrange(delta_len):
            code = delta[line_no][0:2]

            if code not in ["- ", "+ ", "? "]:
                break
            else:
                if not dmesg_buffer_full:
                    dmesg_buffer_full = True
                    debug("Detected full dmesg buffer")
        else:
            debug("No common line between old and new dmesg seen")
            # This is a problem, as we don't know what else has whizzed off the
            # top of the buffer. Arguably, if the dmesg can be completely
            # replaced in the time of a benchmark, we have issues anyway.
            return True

        # As we enter this loop, line_no is the index of the first line that
        # didn't fall off the top of the dmesg.
        while line_no < delta_len:
            rec = delta[line_no]
            code = rec[0:2]
            line = rec[2:]

            if code == "  ":  # in both
                pass
            elif code == "+ ":  #  new line in dmesg
                if not self.filter_new_dmesg_line(line, patterns):
                    # this is a new line which we did not expect
                    new_lines.append(line)
            else:
                assert False  # should not happen

            line_no += 1

        rv = False
        if new_lines:
            # dmesg changed!
            warn_s = ("New dmesg lines:\n%s" % "\n  ".join(new_lines))
            log_and_mail(self.mailer, warn, "dmesg changed", warn_s,
                         manifest=manifest)
            rv = True  # i.e. a (potential) error occurred

        return rv

    def wait_for_temperature_sensors(self, testing=False):
        """A polling loop waiting for temperature sensors to return (close) to
        their starting values.

        When 'testing' is True, only one iteration of the wait loop will
        run (used only in unit tests)."""

        if self.quick_mode:
            warn("Not waiting for temperature sensors (--quick)")
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
                self.sleep(1)
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
        self.audit["krun_version"] = util.get_git_version()
        self.audit["cli_args"] = sys.argv

    def bench_cmdline_adjust(self, args, env_dct):
        """Prepends various arguments to benchmark invocation.

        Currently deals with:
          * CPU pinning (if available)
          * Adding libkruntime.so to linker path

        It does not deal with changing user, as this is done one
        level up in the wrapper script."""

        # platform specific env changes to apply (if any)
        combine_env = env_dct.copy()
        changes = self.bench_env_changes()
        EnvChange.apply_all(changes, combine_env)

        return self.adjust_env_cmd(combine_env) + args

    @abstractmethod
    def _change_user_args(self, user="root"):
        pass

    def change_user_args(self, user="root"):
        return self._change_user_args(user)

    @abstractmethod
    def process_priority_args(self):
        pass

    @abstractmethod
    def get_reboot_cmd(self):
        pass

    def save_power(self):
        debug("Save power")
        self._save_power()

    def clear_cpu_pinning(self):
        pass

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

    @abstractmethod
    def is_virtual(self):
        """Attempt to decide if Krun is running in a virtual machine.

        Returns a boolean.
        """
        pass

    @abstractmethod
    def make_fresh_krun_user(self):
        """Make the krun user account from scratch, forcibly deleting any
        remnants of any existing krun user."""
        pass

    @abstractmethod
    def get_num_temperature_sensors(self):
        """Get the number of temperature sensors"""
        pass


class UnixLikePlatform(BasePlatform):
    """A UNIX-like platform, e.g. Linux, BSD, Solaris"""

    FORCE_LIBRARY_PATH_ENV_NAME = "LD_LIBRARY_PATH"
    REBOOT = "reboot"
    NICE_CMD = "/usr/bin/nice"

    def __init__(self, mailer, config):
        self.change_user_cmd = find_executable("sudo")
        if self.change_user_cmd is None:
            fatal("Could not find sudo!")

        BasePlatform.__init__(self, mailer, config)

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
        if not self.no_user_change:
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
        self.sleep(SYNC_SLEEP_SECS)

    def extra_userdel_args(self):
        return []

    def make_fresh_krun_user(self):
        try:
            pwd.getpwnam(BENCHMARK_USER)
        except KeyError:
            pass  # krun user does not exist, fine.
        else:
            # krun user does exist, remove it
            debug("Delete krun user")
            args = self.change_user_args("root") + ["userdel", "-r"] + \
                self.extra_userdel_args() + [BENCHMARK_USER]
            run_shell_cmd(" ".join(args))

        # Create fresh user
        debug("Create krun user")
        args = self.change_user_args("root") + ["useradd", "-m", BENCHMARK_USER]

        run_shell_cmd(" ".join(args))

        # This should now not raise
        try:
            pwd.getpwnam(BENCHMARK_USER)
        except KeyError:
            fatal("Creating krun user failed")


class OpenBSDPlatform(UnixLikePlatform):
    FIND_TEMP_SENSORS_CMD = "sysctl -a | grep -e 'hw\.sensors\..*\.temp'"
    GET_SETPERF_CMD = "sysctl hw.setperf"
    VIO_DMESG_PATTERN = "virtio[0-9]+ at"

    # flags to set OpenBSD MALLOC_OPTIONS to. We disable anything that could
    # possibly introduce non-determinism or extra computation.
    # See malloc.conf(5) and src/lib/libc/stdlib/malloc.c for more info.
    # Although 'F' would improve determinism, it seems to impact performance
    # (enough for us to care).
    MALLOC_OPTS = "cfgrux"
    MALLOC_CONF = "/etc/malloc.conf"

    def __init__(self, mailer, config):
        UnixLikePlatform.__init__(self, mailer, config)

    def find_temperature_sensors(self):
        lines = self._get_sysctl_sensor_lines()
        sensors = []
        if lines is not None:
            for line in lines.split("\n"):
                elems = line.split("=")

                if len(elems) != 2:
                    fatal("Malformed sysctl line: '%s'" % line)

                sensors.append(elems[0].strip())
        self.temp_sensors = sensors

    def get_num_temperature_sensors(self):
        return len(self.temp_sensors)

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

        # apmd needs to be enabled for this code to work
        args = self.change_user_args("root") + ["rcctl", "start", "apmd"]
        run_shell_cmd(" ".join(args))

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
        out, err, _ = run_shell_cmd(self.GET_SETPERF_CMD)
        elems = out.split("=")
        if len(elems) != 2:
            if "value is not available" in err:
                # sysctl returns 0 even on error. OpenBSD bug?
                warn("hw.setperf is not available -- can't check apm state")

                # Try anyway
                out, _, _ = run_shell_cmd("apm -H")
                return
            else:
                fatal("Can't run: %s" % self.GET_SETPERF_CMD)

        if elems[1].strip() != "100":
            debug("hw.setperf is '%s' not '100'" % elems[1])
            adjust = True

        if adjust:
            debug("adjusting performance mode")
            out, _, _ = run_shell_cmd("apm -H")
            self._check_apm_state()  # should work this time

    def _get_sysctl_sensor_lines(self):
        # separate for test mocking
        out, err, rc = run_shell_cmd(self.FIND_TEMP_SENSORS_CMD, failure_fatal=False)
        if rc == 0:
            return out
        elif rc == 1:
            # not really an error. Actually no lines matched, thus no sensors.
            warn("System does not appear to have temperature sensors.")
        else:
            fatal("Failed to run: %s" % self.FIND_TEMP_SENSORS_CMD)

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

        if os.path.lexists(OpenBSDPlatform.MALLOC_CONF):
            fatal("%s exists. Please remove it" %
                  OpenBSDPlatform.MALLOC_CONF)

        from krun import EntryPoint
        ep = EntryPoint("check_openbsd_malloc_options.so")

        from krun.vm_defs import NativeCodeVMDef
        vd = NativeCodeVMDef()

        util.spawn_sanity_check(self, ep, vd, "OpenBSD malloc options",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def pin_process_args(self):
        return []  # not supported on OpenBSD

    def is_virtual(self):
        """If we see a vio(4) disk in the dmesg, this is a virtual machine"""

        dmesg_lines = self._collect_dmesg_lines()
        comp_pat = re.compile(OpenBSDPlatform.VIO_DMESG_PATTERN)
        return any(comp_pat.match(l) for l in dmesg_lines)

    def default_dmesg_whitelist(self):
        # PyPy uses write+executable pages, which causes this dmesg entry
        # in OpenBSD-current (as of around 6.0-beta)
        return ["^.*\([0-9]+\): .*W\^X violation$"]


class LinuxPlatform(UnixLikePlatform):
    """Deals with aspects generic to all Linux distributions. """

    HWMON_CHIPS_GLOB = "/sys/class/hwmon/hwmon[0-9]"
    CPU_GOV_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_governor"
    TURBO_DISABLED = "/sys/devices/system/cpu/intel_pstate/no_turbo"
    PERF_SAMPLE_RATE = "/proc/sys/kernel/perf_event_max_sample_rate"
    CPU_SCALER_FMT = "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_driver"
    KERNEL_ARGS_FILE = "/proc/cmdline"
    ASLR_FILE = "/proc/sys/kernel/randomize_va_space"
    ASLR_MODE = 2
    CSET_CMD = "/usr/bin/cset"
    USER_CSET_DIR = "/cpusets/user"
    RESTRICT_DMESG_FILE = "/proc/sys/kernel/dmesg_restrict"
    UNKNOWN_SENSOR_CHIP_NAME = "__krun_unknown_chip_name"
    TEMP_SENSOR_INPUT_GLOB = "temp[0-9]*_input"
    IA32_MISC_ENABLE = 0x1a0
    IA32_MISC_ENABLE_TURBO_DISABLE = 1 << 38
    OVERCOMMIT_POLICY_MIB = "vm.overcommit_memory"
    OVERCOMMIT_POLICY_OFF = 2

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
        # runnable process. This enables the tickless functionality, but the
        # system admin must manually specify on adaptive-tick CPUs via
        # the kernel command line. By default, no CPUs are adaptive tick,
        # so we insist also upon CONFIG_NO_HZ_FULL_ALL.
        "CONFIG_NO_HZ_FULL": True,

        # Same as CONFIG_NO_HZ_FULL, but forces all CPUs apart from the
        # boot CPU into adaptive tick mode. This is what we want to
        # see enabled. Note that you cannot have all CPUs in adaptive-tick.
        "CONFIG_NO_HZ_FULL_ALL": True,
    }

    def __init__(self, mailer, config):
        self.temp_sensor_map = None
        self.virt_what_cmd = self._find_virt_what()
        UnixLikePlatform.__init__(self, mailer, config)
        self.num_cpus = self._get_num_cpus()
        self._load_modules(["msr"])

    def _load_modules(self, modules):
        for mod in modules:
            debug("Loading kernel module: %s" % mod)
            args = self.change_user_args("root") + ["modprobe", mod]
            run_shell_cmd(" ".join(args))

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

    @staticmethod
    def _collect_temperature_sensor_globs():
        """Collects the sysfs info needed to enumerate temperature sensors.
        Separate to enable test mocking"""

        res = {}
        hwmons = glob.glob(LinuxPlatform.HWMON_CHIPS_GLOB)
        for chip in hwmons:
            name_path = os.path.join(chip, "name")
            try:
                with open(name_path) as fh:
                    chip_name = fh.read().strip()
            except IOError:
                chip_name = None

            # Check our super-obscure un-named chip string doesn't arise in the wild!
            assert chip_name != LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME

            inputs_glob = os.path.join(chip, LinuxPlatform.TEMP_SENSOR_INPUT_GLOB)
            res[chip] = chip_name, list(glob.glob(inputs_glob))
        return res

    def find_temperature_sensors(self):
        """Detect sensors using the hwmon sysfs framework

        It's unclear as to whether the sensors may move between reboots, so we
        have to roll our own sensor identifiers. We are not fussy, and use as
        many sensors as we can find"""

        # maps our identifier to actual sysfs filename
        sensor_tree = {}  # chip_id -> sensor_id -> sysfs_path
        # chip IDs are pairs: (chip_name, num_sensors)
        duplicate_chip_ids = set()

        for chip, (chip_name, chip_sensors) in \
                LinuxPlatform._collect_temperature_sensor_globs().iteritems():
            if chip_name is None:
                debug("Un-named temperature sensor chip found.")
                debug("Naming the chip: '%s'" % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME)
                chip_name = LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME

            chip_id = (chip_name, len(chip_sensors))
            if chip_id in sensor_tree:
                info("Found duplicate chips named '%s' with %s temperature sensor(s)" % chip_id)
                # Ignore all chips with this ID
                duplicate_chip_ids.add(chip_id)
                del sensor_tree[chip_id]
                continue
            elif chip_id in duplicate_chip_ids:
                info("Found another chip named '%s' with %s temperature sensor(s)" % chip_id)
                continue

            sensor_tree[chip_id] = {}
            for sysfs_path in chip_sensors:
                sensor_id = (chip_id[0], str(chip_id[1]), os.path.basename(sysfs_path))
                assert sensor_id not in sensor_tree[chip_id]
                sensor_tree[chip_id][sensor_id] = sysfs_path

        # flatten the tree into a dict: sensor_id -> sysfs_path
        sensor_map = {}
        for chip_id, sensors in sensor_tree.iteritems():
            for sensor_id, sysfs_path in sensors.iteritems():
                assert sensor_id not in sensor_map
                sensor_map[":".join(sensor_id)] = sysfs_path

        debug("Detected temperature sensors: %s" % sensor_map)
        self.temp_sensors = sensor_map.keys()
        self.temp_sensor_map = sensor_map

    def get_num_temperature_sensors(self):
        return len(self.temp_sensors)

    def _get_num_cpus(self):
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

        if self.config.ENABLE_PINNING:
            self._check_cset_installed()
            # Clear any leftover cpu pinning since it will break taskset
            self.clear_cpu_pinning()
        self._check_isolcpus()
        self._check_cpu_governor()
        self._check_cpu_scaler()
        self._check_perf_samplerate()
        if not self.no_tickless_check:
            self._check_tickless_kernel()
        self._check_aslr_enabled()
        self._check_dmesg_unrestricted()
        if self.config.ENABLE_PINNING:
            self._check_cset_shield()
        self._check_overcommit()

    def _find_virt_what(self):
        debug("Check virt-what is installed")

        # the tool may not be in the path for an unpriveleged user
        ec = EnvChangeAppend("PATH", "/usr/sbin")
        ec.apply(os.environ)

        from distutils.spawn import find_executable
        exe = find_executable("virt-what")
        if exe is None:
            fatal("virt-what is not installed")
        return exe

    def clear_cpu_pinning(self):
        debug("Clearing cpuset")
        args = self.change_user_args() + [LinuxPlatform.CSET_CMD, "shield", "-r"]
        out, _, _ = run_shell_cmd(" ".join(args), failure_fatal=False)
        debug(out)

    # separate for testing
    def _configure_cset_shield_args(self):
        """Returns the commands (as a list of list of args)
        needed to set up/destroy a shield"""

        if self.config.ENABLE_PINNING:
            # create shield on all cores but boot core.
            # OK to create shield when one is already created.
            cpus = "1-%s" % (self.num_cpus - 1)
            cmd1 =  self.change_user_args("root") + \
                [LinuxPlatform.CSET_CMD, "shield", "-c", cpus]
            # move as many kernel threads as you can, please
            cmd2 = [LinuxPlatform.CSET_CMD, "shield", "-k", "on"]
            return [cmd1, cmd2]
        else:
            # destroy shield (if existing)
            if os.path.exists(LinuxPlatform.USER_CSET_DIR):
                return [self.change_user_args("root") + \
                        [LinuxPlatform.CSET_CMD, "shield", "-r"]]
            else:
                return []  # no commands

    def _check_cset_shield(self):
        """Create/reset and check cset sheild status"""

        debug("create/check/remove cset shield")
        cmds = self._configure_cset_shield_args()
        for args in cmds:
            cmd = " ".join(args)
            out, _, _ = run_shell_cmd(cmd)
            debug(out)  # cset is quite chatty on stdout

    def _check_dmesg_unrestricted(self):
        debug("Checking if dmesg buffer is restricted")

        if os.path.exists(LinuxPlatform.RESTRICT_DMESG_FILE):
            cmd = "%s cat %s" % (self.change_user_cmd,
                                 LinuxPlatform.RESTRICT_DMESG_FILE)
            out, _, _ = run_shell_cmd(cmd)
            if int(out) == 0:
                debug("%s: 0" % LinuxPlatform.RESTRICT_DMESG_FILE)
                return

            debug("%s: 1 -> 0" % LinuxPlatform.RESTRICT_DMESG_FILE)
            cmd = "%s sh -c 'echo 0 > %s'" % \
                (self.change_user_cmd, LinuxPlatform.RESTRICT_DMESG_FILE)
            run_shell_cmd(cmd)
        else:
            debug("%s does not exist, assuming dmesg is not restricted" %
                  LinuxPlatform.RESTRICT_DMESG_FILE)

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

            path = LinuxPlatform.CPU_GOV_FMT % cpu_n
            try:
                fh = open(path, "r")
            except IOError:
                # On some virtulised systems, this info is unavailable.
                if self.is_virtual():
                    warn("Virtualised system doesn't allow Krun to check the CPU governor.")
                    return
                else:
                    fatal("Unable to check the CPU governor (via %s)." % path)

            v = fh.read().strip()
            fh.close()

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

    def _read_ia32_misc_enable_msr(self):
        """Returns the the IA32_MISC_ENABLE MSR values. One for each core"""

        args = self.change_user_args("root") + \
            ["rdmsr", "--all", hex(LinuxPlatform.IA32_MISC_ENABLE)]
        out, _, rv = run_shell_cmd(" ".join(args))
        vals = [int(x, 16) for x in out.strip().splitlines()]
        assert len(vals) == self.num_cpus
        return vals

    def _check_cpu_scaler(self):
        """Check the correct CPU scaler is in effect"""

        for cpu_n in xrange(self.num_cpus):
            # Check CPU scaler
            debug("Checking CPU scaler for CPU%d" % cpu_n)

            path = LinuxPlatform.CPU_SCALER_FMT % cpu_n
            try:
                fh = open(path, "r")
            except IOError:
                if self.is_virtual():
                    warn("Virtualised system doesn't allow Krun to check the CPU scaler")
                    return
                else:
                    fatal("Unable to check the CPU scaler (via %s)." % path)

            v = fh.read().strip()
            fh.close()

            if v != "acpi-cpufreq":
                if v == "intel_pstate":
                    if self.no_pstate_check:
                        warn("Ignoring enabled P-states (--no-pstate-check)")
                        return

                    scaler_files = ["  * " + LinuxPlatform.CPU_SCALER_FMT % x for
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

        # On some systems, you cannot turn turbo boost off in the BIOS, so we
        # forcibly turn off turbo mode via the IA32_MISC_ENABLE MSR for cores
        # which report as "supporting" turbo mode.
        debug("Checking 'turbo boost' is disabled")

        # If this file exists, then the pstate driver is loaded. It shouldn't be!
        assert not os.path.exists(LinuxPlatform.TURBO_DISABLED)

        # Query each core asking if it supports turbo mode. If it says "yes",
        # then we turn it off. Depending on the CPU, the turbo settings may be
        # shared across more than a single core. To be safe, we assume there is
        # no sharing.
        query_program_path = os.path.join(UTILS_DIR, "query_turbo")
        for core in xrange(self.num_cpus):
            args = ["taskset", "-c", str(core), query_program_path]
            out, _, _ = run_shell_cmd(" ".join(args))
            if int(out.strip()) == 0:
                debug("CPU %d doesn't support turbo boost, or it is already disabled" % core)
                continue

            debug("CPU supports turbo boost and it is enabled. Disabling...")
            val = self._read_ia32_misc_enable_msr()[core]
            new_val = val | LinuxPlatform.IA32_MISC_ENABLE_TURBO_DISABLE
            args = self.change_user_args("root") + \
                ["wrmsr", "-p", str(core), hex(LinuxPlatform.IA32_MISC_ENABLE), hex(new_val)]
            run_shell_cmd(" ".join(args))

        # Sanity check the update
        vals = self._read_ia32_misc_enable_msr()
        for core in xrange(self.num_cpus):
            # MSR disable bit is on?
            assert (vals[core] & LinuxPlatform.IA32_MISC_ENABLE_TURBO_DISABLE) != 0
            # Core reports not supporting turbo now?
            args = ["taskset", "-c", str(core), query_program_path]
            out, _, _ = run_shell_cmd(" ".join(args))
            assert int(out.strip()) == 0

    def _check_aslr_enabled(self):
        """Check ASLR is cranked to level 2

        For info on ASLR modes, see randomize_va_space in:
        https://www.kernel.org/doc/Documentation/sysctl/kernel.txt

        Note that turning on ASLR does nothing for PIE (position independent
        executable -- randomisation of the .text section) unless the binary is
        also compiled with a special flag.
        """

        debug("Checking ASLR is on")
        for rep in 1, 2:
            with open(LinuxPlatform.ASLR_FILE, "r") as fh:
                val = fh.read().strip()
            if val == str(LinuxPlatform.ASLR_MODE):
                return  # OK!
            else:
                if rep == 2:
                    fatal("Failed to adjust ASLR setting")
                else:
                    # setting is wrong, adjust.
                    debug("Adjust ASLR")
                    cmd = "%s sh -c 'echo %s > %s'" % \
                        (self.change_user_cmd, LinuxPlatform.ASLR_MODE,
                         LinuxPlatform.ASLR_FILE)
                    stdout, stderr, rc = run_shell_cmd(cmd)
        assert False  # unreachable

    def collect_audit(self):
        BasePlatform.collect_audit(self)

        # Extra CPU info, some not in dmesg. E.g. CPU cache size.
        self.audit["cpuinfo"] = run_shell_cmd("cat /proc/cpuinfo")[0]

    def get_reboot_cmd(self):
        cmd = self.change_user_args()
        cmd.append(self.REBOOT)
        return cmd

    def pin_process_args(self):
        """Pin to a set of isolated (via cset shield), adaptive tick CPUs."""

        if self.num_cpus == 1:
            fatal("not enough CPUs to pin")

        # cset shielding requires root
        # double dash signifies end of cset args
        return self.change_user_args("root") + \
            [LinuxPlatform.CSET_CMD, "shield", "-e", "--"]

    def _check_cset_installed(self):
        debug("Check cset is installed")

        from distutils.spawn import find_executable
        if not find_executable("cset"):
            fatal("cset is not installed (needed for pinning).")

    def sanity_checks(self):
        UnixLikePlatform.sanity_checks(self)
        self._sanity_check_cpu_affinity()
        self._sanity_check_scheduler()

    def _sanity_check_cpu_affinity(self):
        from krun.vm_defs import NativeCodeVMDef
        from krun import EntryPoint

        if self.config.ENABLE_PINNING:
            ep = EntryPoint("check_linux_cpu_affinity_pinned.so")
        else:
            ep = EntryPoint("check_linux_cpu_affinity_not_pinned.so")

        vd = NativeCodeVMDef()
        util.spawn_sanity_check(self, ep, vd, "CPU affinity",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def _sanity_check_scheduler(self):
        from krun.vm_defs import NativeCodeVMDef
        from krun import EntryPoint

        ep = EntryPoint("check_linux_scheduler.so")
        vd = NativeCodeVMDef()
        util.spawn_sanity_check(self, ep, vd, "Scheduler",
                                force_dir=PLATFORM_SANITY_CHECK_DIR)

    def _check_isolcpus(self):
        """Checks that the isolcpus kernel arg is not in use.

        We used to use isolcpus to run processes on isolated cores, but this --
        at the time -- had issues for multi-threaded programs:
        https://bugzilla.kernel.org/show_bug.cgi?id=116701

        Now we achieve the correct behaviour using a cset shield, which is
        arguably better anyway, as it moves (some) kernel threads off the
        benchmarking cores too.
        """

        debug("Check isolcpus not in use")

        all_args = self._get_kernel_cmdline()

        args = all_args.split(" ")
        for arg in args:
            if "=" not in arg:
                continue

            key, val = arg.split("=", 1)
            assert val != ""

            if key != "isolcpus":
                continue

            got_cpus = list(sorted(val.split(",")))
            break
        else:
            got_cpus = []

        if got_cpus != []:
            self._fatal_kernel_arg(
                "isolcpus", "isolcpus should not be in the kernel command line"
            )

    def _check_overcommit(self):
        """
        Check that memory overcommit is totally disabled.
        """

        debug("Checking over-commit policy")

        def get_overcommit_policy():
            cmd = "%s sysctl %s" % (self.change_user_cmd, LinuxPlatform.OVERCOMMIT_POLICY_MIB)
            out, _, _ = run_shell_cmd(cmd, failure_fatal=False)
            return int(out.strip().split("=")[1])

        if get_overcommit_policy() != LinuxPlatform.OVERCOMMIT_POLICY_OFF:
            debug("Over-commit not disabled. Disabling now.")
            cmd = "%s sysctl %s=%s" % (self.change_user_cmd,
                                       LinuxPlatform.OVERCOMMIT_POLICY_MIB,
                                       LinuxPlatform.OVERCOMMIT_POLICY_OFF)
            run_shell_cmd(cmd, failure_fatal=False)
            assert get_overcommit_policy() == LinuxPlatform.OVERCOMMIT_POLICY_OFF
        else:
            debug("Over-commit was already disabled.")

    def default_dmesg_whitelist(self):
        return [
                # Bringing the network up and down on Linux (which some
                # experiments may wish to do) makes some noise. Ignore.
                "^.*ADDRCONF\(NETDEV_UP\)",
                "^.*ADDRCONF\(NETDEV_CHANGE\)",
                "^.*NIC Link is (Up|Down)",
                "^.*irq.* for MSI/MSI-X",
                "^.*eth[0-9]: link (down|up)",
                "^.*eth[0-9]: Link is (up|down).*",
                "^.*eth[0-9]: Flow control is (on|off).*",
                "^.*eth[0-9]: EEE is (enabled|disabled).*",
                # Graphics card goes into powersave
                "^.*\[drm\] Enabling RC6 states",
            ]

    def _sched_get_priority_max(self):
        # If we later support other operating systems which too support static
        # thread priorities, then move this method into a super-class and call
        # out to C to sched_get_priority_max(2).
        return 99  # Linux specific maximum

    def is_virtual(self):
        if os.environ.get("TRAVIS") == "true":
            return True

        # Needs to be run as root
        args = self.change_user_args("root") + [self.virt_what_cmd]

        virt_facts, _, _ = run_shell_cmd(" ".join(args))
        virt_facts = virt_facts.strip()

        debug("detect-virt: %s" % virt_facts)

        # If any virtualisation fact is inferred, this is a virtualised host.
        # Therefore an empty string means we are on bare-metal.
        if virt_facts == "":
            return False
        else:
            return True

    def extra_userdel_args(self):
        # Needed on Linux because the default mail spool ownership causes
        # non-zero userdel exit status.
        return ["-f"]  # force


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
              "Set/change/remove `%s` in the kernel arguments.\n"
              "To do this on Debian:\n"
              "  * Edit /etc/default/grub\n"
              "  * Amend GRUB_CMDLINE_LINUX_DEFAULT\n"
              "  * Run `sudo update-grub`\n"
              "%s" % (prefix, arg, suffix))


def detect_platform(mailer, config):
    plat_name = sys.platform
    if plat_name.startswith("linux"):
        if os.path.exists("/etc/debian_version"):
            return DebianLinuxPlatform(mailer, config)
        else:
            fatal("Unknown Linux platform")
    elif plat_name.startswith("openbsd"):
        return OpenBSDPlatform(mailer, config)
    else:
        fatal("I don't have support for your platform")
