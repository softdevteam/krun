# Tools for detecting platform and OS.

import sys
import os


# Note the subtle difference between OS and platform
PLATFORM_UNKNOWN = 0
PLATFORM_LINUX = 1
PLATFORM_OPENBSD = 2

OS_UNKNOWN = 0
OS_DEBIAN = 1
OS_OPENBSD = 2


def detect_platform():
    if sys.platform.startswith("linux"):
        return PLATFORM_LINUX
    else:
        return PLATFORM_UNKNOWN


def detect_os():
    if os.path.exists("/etc/debian_version"):
        assert detect_platform() == PLATFORM_LINUX
        return OS_DEBIAN
    else:
        return OS_UNKNOWN
