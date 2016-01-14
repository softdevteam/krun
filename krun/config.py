from logging import error

import os.path
import time

from krun import LOGFILE_FILENAME_TIME_FORMAT
from krun.util import fatal

# XXX Add the rest of the required fields
CHECK_FIELDS = ["HEAP_LIMIT", "STACK_LIMIT"]

class Config(object):
    """All configuration for a Krun benchmark.
    Includes CLI args as well as configuration from .krun files.
    """

    def __init__(self, config_file=None):
        # config defaults go here
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

        if config_file is not None:
            self.read_from_file(config_file)

    def read_from_string(self, config_str):
        config_dict = {}
        try:
            exec(config_str, config_dict)
        except Exception as e:
            error("error importing config file:\n%s" % str(e))
            raise
        self.__dict__.update(config_dict)
        self.filename = ""
        self.text = config_str

    def read_from_file(self, config_file):
        assert config_file.endswith(".krun")
        config_dict = {}
        try:
            execfile(config_file, config_dict)
        except Exception as e:
            error("error importing config file:\n%s" % str(e))
            raise

        for key in CHECK_FIELDS:
            if key not in config_dict:
                fatal("Config file is missing a %s" % key)

        self.__dict__.update(config_dict)
        self.filename = config_file
        with open(config_file, "r") as fp:
            self.text = fp.read()

    def log_filename(self, resume=False):
        assert self.filename.endswith(".krun")
        if resume:
            config_mtime = time.gmtime(os.path.getmtime(self.filename))
            tstamp = time.strftime(LOGFILE_FILENAME_TIME_FORMAT, config_mtime)
        else:
            tstamp = time.strftime(LOGFILE_FILENAME_TIME_FORMAT)
        return self.filename[:-5] + "_%s.log" % tstamp

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
                (self.N_EXECUTIONS == other.N_EXECUTIONS))
