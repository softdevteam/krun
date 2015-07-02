ANSI_RED = '\033[91m'
ANSI_GREEN = '\033[92m'
ANSI_MAGENTA = '\033[95m'
ANSI_CYAN = '\033[36m'
ANSI_RESET = '\033[0m'


class EntryPoint(object):
    def __init__(self, target, subdir=None):
        self.target = target
        self.subdir = subdir
