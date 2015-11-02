from krun import ABS_TIME_FORMAT, UNKNOWN_TIME_DELTA, UNKNOWN_ABS_TIME

import datetime

class TimeEstimateFormatter(object):
    def __init__(self, seconds):
        """Generates string representations of time estimates.
        Args:
        seconds -- estimated seconds into the future. None for unknown.
        """
        self.start = datetime.datetime.now()
        if seconds is not None:
            self.delta = datetime.timedelta(seconds=seconds)
            self.finish = self.start + self.delta
        else:
            self.delta = None
            self.finish = None

    @property
    def start_str(self):
        return str(self.start.strftime(ABS_TIME_FORMAT))

    @property
    def finish_str(self):
        if self.finish is not None:
            return str(self.finish.strftime(ABS_TIME_FORMAT))
        else:
            return UNKNOWN_ABS_TIME

    @property
    def delta_str(self):
        if self.delta is not None:
            return str(self.delta).split(".")[0]
        else:
            return UNKNOWN_TIME_DELTA
