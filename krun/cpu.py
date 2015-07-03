# Various CPU related abstrations

import time
import os
from krun.detect import detect_platform, PLATFORM_LINUX

# Checking the CPU is running at full-speed
# -----------------------------------------
# Typically you need to be root to change the power settings, so we just
# crash out and let the user sort it out in the case that the CPU is not
# screaming along at max speed.

LINUX_GOV_FILE = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"

class CPUNotThrottledError(Exception):
    pass

def check_cpu_throttled():
    print("Checking CPU is throttled")
    p = detect_platform()
    if p == PLATFORM_LINUX:
        check_cpu_throttled_linux()
    else:
        raise NotImplementedError("I don't know how to check your CPU")

def check_cpu_throttled_linux():
    with open(LINUX_GOV_FILE, "r") as fh:
        v = fh.read().strip()

    if v != "performance":
        raise CPUNotThrottledError(("Expected 'performance' got '%s'. "
                                    "Use cpufreq-set from the "
                                    "cpufrequtils package") % v)


# Waiting for the CPU to cool down
# --------------------------------
# Wait until the CPU is within a number of degrees of its starting temperature.

class BaseCPUTempRegulator(object):
    MANDATORY_WAIT = 1
    POLL_FREQ = 5

    def __init__(self):
        self.take_initial_readings()

    def wait_until_cool(self):
        time.sleep(BaseCPUTempRegulator.MANDATORY_WAIT)
        msg_shown = False
        while True:
            cool, reason = self.has_cooled()
            if cool:
                break

            # if we get here, CPU is too hot!
            if not msg_shown:
                print("CPU is running hot.")
                print(reason)
                print("Waiting to cool")
                msg_shown = True

            time.sleep(BaseCPUTempRegulator.POLL_FREQ)

    # The interfaces subclasses must provide:
    def take_readings(self):
        raise NotImplementedError("abstract")

    def take_initial_readings(self):
        raise NotImplementedError("abstract")

    def has_cooled(self):
        raise NotImplementedError("abstract")

class LinuxCPUTempRegulator(BaseCPUTempRegulator):
    THERMAL_BASE = "/sys/class/thermal/"

    # Temperature files under /sys measure in millidegrees
    # https://www.kernel.org/doc/Documentation/thermal/sysfs-api.txt
    THRESHOLD = 1000  # therefore one degree

    def __init__(self):
        self.zones = self._find_thermal_zones()
        BaseCPUTempRegulator.__init__(self)

    def _find_thermal_zones(self):
        return [x for x in os.listdir(LinuxCPUTempRegulator.THERMAL_BASE) if
                x.startswith("thermal_zone")]

    def take_initial_readings(self):
        self.initial_readings = self.take_readings()

    def _read_zone(self, zone):
        fn = os.path.join(LinuxCPUTempRegulator.THERMAL_BASE, zone, "temp")
        with open(fn, "r") as fh:
            return int(fh.read())

    def take_readings(self):
        return [self._read_zone(z) for z in self.zones]

    def has_cooled(self):
        """returns tuple: cool * str_reason_if_false"""

        readings = self.take_readings()
        for i in range(len(self.initial_readings)):
            if readings[i] - self.initial_readings[i] - self.THRESHOLD > 0:
                reason = "Zone 1 started at %d but is now %d" % \
                    (self.initial_readings[i], readings[i])
                return (False, reason)  # one or more sensor too hot
        return (True, None)

def new_cpu_temp_regulator():
    p = detect_platform()
    if p == PLATFORM_LINUX:
        return LinuxCPUTempRegulator()
    else:
        raise NotImplementedError("I don't know how to measure CPU "
                                  "temperature for your platform")
