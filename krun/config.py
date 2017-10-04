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

import os.path
import time
import sys
import traceback

from krun import LOGFILE_FILENAME_TIME_FORMAT
from krun.util import fatal

# XXX Add the rest of the required fields
CHECK_FIELDS = ["HEAP_LIMIT", "STACK_LIMIT"]

class Config(object):
    """All configuration for a Krun benchmark.
    Includes CLI args as well as configuration from .krun files.
    """

    def __init__(self, config_file=None):
        # config defaults (variables)
        self.MAIL_TO = list()
        self.MAX_MAILS = 5
        self.VMS = dict()
        self.VARIANTS = dict()
        self.BENCHMARKS = dict()
        self.SKIP = list()
        self.N_EXECUTIONS = 1
        self.filename = config_file
        self.HEAP_LIMIT = None
        self.STACK_LIMIT = None
        self.TEMP_READ_PAUSE = 60
        self.ENABLE_PINNING = False
        self.AMPERF_BUSY_THRESHOLD = None
        self.AMPERF_RATIO_BOUNDS = None
        self.PRE_EXECUTION_CMDS = []
        self.POST_EXECUTION_CMDS = []

        # config defaults (callbacks)
        self.custom_dmesg_whitelist = None

        if config_file is not None:
            self.read_from_file(config_file)

    def _fatal_exception_execing_config(self, exc_info):
        lines = ["error importing config file: %s\n" % str(exc_info[1])]
        for frame in traceback.format_tb(exc_info[2]):
            lines.append(frame)
        fatal("".join(lines))

    def check_config_consistency(self, config_str, filename):
        import difflib
        if self.text != config_str:
            diff = "".join(difflib.unified_diff(
                self.text.splitlines(True), config_str.splitlines(True),
                self.filename, "<cached in %s>" % filename))
            fatal("The experiment is in an inconsistent state as the config"
                  "file %s has changed since it was initially cached in %s"
                  "\n%s" % (
                      self.filename, filename, diff))

    def read_from_file(self, config_file):
        assert config_file.endswith(".krun")
        config_dict = {}
        try:
            execfile(config_file, config_dict)
        except Exception:
            self._fatal_exception_execing_config(sys.exc_info())

        for key in CHECK_FIELDS:
            if key not in config_dict:
                fatal("Config file is missing a %s" % key)

        for vm_name in config_dict["VMS"]:
            if " " in vm_name:
                fatal("VM names must not contain spaces")

        for vm_name in config_dict["BENCHMARKS"]:
            if " " in vm_name:
                fatal("Benchmark names must not contain spaces")

        for variant_name in config_dict["VARIANTS"]:
            if " " in variant_name:
                fatal("Variant names must not contain spaces")

        self.__dict__.update(config_dict)
        self.filename = config_file
        with open(config_file, "r") as fp:
            self.text = fp.read()

        if self.AMPERF_RATIO_BOUNDS and not self.AMPERF_BUSY_THRESHOLD or \
                not self.AMPERF_RATIO_BOUNDS and self.AMPERF_BUSY_THRESHOLD:
                fatal("AMPERF_RATIO_BOUNDS and AMPERF_BUSY_THRESHOLD must either "
                      "both be defined in the config file, or neither")

    def log_filename(self, resume=False):
        assert self.filename.endswith(".krun")
        return self.filename[:-5] + ".log"

    def results_filename(self):  # FIXME: was called output_name in util
        """Makes a result file name based upon the config file name."""
        assert self.filename.endswith(".krun")
        return self.filename[:-5] + "_results.json.bz2"

    def should_skip(self, this_key):
        """Decides if 'this_key' is a benchmark key that will be skipped"""

        this_elems = this_key.split(":")
        if len(this_elems) != 3:
            raise ValueError("bad benchmark key: %s" % this_key)

        for skip_key in self.SKIP:
            skip_elems = skip_key.split(":")

            # Should be triples of: bench * vm * variant
            assert len(skip_elems) == 3 and len(this_elems) == 3

            # Don't mutate this_elems directly, as we need it
            # fresh for future iterations.
            this_elems_copy = this_elems[:]
            for i in range(3):
                if skip_elems[i] == "*":
                    this_elems_copy[i] = "*"

            if skip_elems == this_elems_copy:
                return True # skip

        return False

    def __str__(self):
        return self.text

    def __eq__(self, other):
        # Equality should ignore filename.
        return (isinstance(other, self.__class__) and
                (self.text == other.text) and
                (self.MAIL_TO == other.MAIL_TO) and
                (self.MAX_MAILS == other.MAX_MAILS) and
                (self.VMS == other.VMS) and
                (self.VARIANTS == other.VARIANTS) and
                (self.BENCHMARKS == other.BENCHMARKS) and
                (self.SKIP == other.SKIP) and
                (self.N_EXECUTIONS == other.N_EXECUTIONS) and
                (self.PRE_EXECUTION_CMDS == other.PRE_EXECUTION_CMDS) and
                (self.POST_EXECUTION_CMDS == other.POST_EXECUTION_CMDS))
