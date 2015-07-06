ABS_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
UNKNOWN_TIME_DELTA = "?:??:??"
UNKNOWN_ABS_TIME = "????-??-?? ??:??:??"

class EntryPoint(object):
    def __init__(self, target, subdir=None):
        self.target = target
        self.subdir = subdir
