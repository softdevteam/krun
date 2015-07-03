# Various CPU related abstrations

import time
import os
from krun.util import fatal


class BasePlatform(object):
    CPU_TEMP_MANDATORY_WAIT = 1
    CPU_TEMP_POLL_FREQ = 5

    def wait_until_cpu_cool(self):
        time.sleep(BasePlatform.CPU_TEMP_MANDATORY_WAIT)
        msg_shown = False
        while True:
            cool, reason = self.has_cpu_cooled()
            if cool:
                break

            # if we get here, CPU is too hot!
            if not msg_shown:
                print("CPU is running hot.")
                print(reason)
                print("Waiting to cool")
                msg_shown = True

            time.sleep(BasePlatform.CPU_TEMP_POLL_FREQ)

    # When porting to a new platform, implement the following:
    def take_cpu_temp_readings(self):
        raise NotImplementedError("abstract")

    def set_base_cpu_temps(self):
        raise NotImplementedError("abstract")

    def has_cpu_cooled(self):
        raise NotImplementedError("abstract")

    def check_cpu_throttled(self):
        raise NotImplementedError("abstract")

class LinuxPlatform(BasePlatform):
    THERMAL_BASE = "/sys/class/thermal/"
    CPU_GOV_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"

    # Temperature files under /sys measure in millidegrees
    # https://www.kernel.org/doc/Documentation/thermal/sysfs-api.txt
    THRESHOLD = 1000  # therefore one degree

    def __init__(self):
        self.initial_readings = None
        self.zones = self._find_thermal_zones()
        BasePlatform.__init__(self)

    def _find_thermal_zones(self):
        return [x for x in os.listdir(LinuxPlatform.THERMAL_BASE) if
                x.startswith("thermal_zone")]

    def set_base_cpu_temps(self):
        self.initial_readings = self.take_cpu_temp_readings()

    def _read_zone(self, zone):
        fn = os.path.join(LinuxPlatform.THERMAL_BASE, zone, "temp")
        with open(fn, "r") as fh:
            return int(fh.read())

    def take_cpu_temp_readings(self):
        return [self._read_zone(z) for z in self.zones]

    def has_cpu_cooled(self):
        """returns tuple: cool * str_reason_if_false"""

        if self.initial_readings is None:
            fatal("Base CPU temperature was not set")

        readings = self.take_cpu_temp_readings()
        for i in range(len(self.initial_readings)):
            if readings[i] - self.initial_readings[i] - self.THRESHOLD > 0:
                reason = "Zone 1 started at %d but is now %d" % \
                    (self.initial_readings[i], readings[i])
                return (False, reason)  # one or more sensor too hot
        return (True, None)

    def check_cpu_throttled(self):
        with open(LinuxPlatform.CPU_GOV_FILE, "r") as fh:
            v = fh.read().strip()

        if v != "performance":
            fatal(("Expected 'performance' got '%s'. "
                   "Use cpufreq-set from the cpufrequtils package") % v)

class DebianLinuxPlatform(LinuxPlatform):
    pass

def platform():
    if os.path.exists("/etc/debian_version"):
        return DebianLinuxPlatform()
    else:
        fatal("I don't have support for your platform")
