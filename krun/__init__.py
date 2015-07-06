ANSI_RED = '\033[91m'
ANSI_GREEN = '\033[92m'
ANSI_MAGENTA = '\033[95m'
ANSI_CYAN = '\033[36m'
ANSI_RESET = '\033[0m'

ABS_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
UNKNOWN_TIME_DELTA = "?:??:??"
UNKNOWN_ABS_TIME = "????-??-?? ??:??:??"

class EntryPoint(object):
    def __init__(self, target, subdir=None):
        self.target = target
        self.subdir = subdir
