ABS_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
LOGFILE_FILENAME_TIME_FORMAT = "%Y%m%d_%H%M%S"
UNKNOWN_TIME_DELTA = "?:??:??"
UNKNOWN_ABS_TIME = "????-??-?? ??:??:??"

class EntryPoint(object):

    def __init__(self, target, subdir=None):
        self.target = target
        self.subdir = subdir

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                (self.target == other.target) and
                (self.subdir == other.subdir))
