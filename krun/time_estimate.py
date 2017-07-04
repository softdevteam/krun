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

def now_str():
    """Just return the time now (formatted)"""

    return str(datetime.datetime.now().strftime(ABS_TIME_FORMAT))
