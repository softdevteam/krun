from krun.audit import Audit
from krun.config import Config
from logging import debug, info
from krun.util import fatal

import bz2  # decent enough compression with Python 2.7 compatibility.
import json


class Results(object):
    """Results of a Krun benchmarking session.
    Can be serialised to disk.
    """

    def __init__(self, config, platform, results_file=None):
        self.config = config

        # Maps key to results:
        # "bmark:vm:variant" -> [[e0i0, e0i1, ...], [e1i0, e1i1, ...], ...]
        self.data = dict()
        self.reboots = 0

        # Instrumentation counters
        # "bmark:vm:variant" ->
        #     (instrumentation name -> [[e0i0, e0i1, ...], [e1i0, e1i1, ...], ...])
        self.inst_data = {}

        # Record how long execs are taking so we can give the user a rough ETA.
        # Maps "bmark:vm:variant" -> [t_0, t_1, ...]
        self.eta_estimates = dict()

        # error_flag is flipped when a (non-fatal) error or warning occurs.
        # When Krun finishes and this flag is true, a message is printed,
        # thus prompting the user to investigate.
        self.error_flag = False

        # Fill in attributes from the config, platform and prior results.
        if self.config is not None:
            self.filename = self.config.results_filename()
            self.init_from_config()
        if platform is not None:
            self.starting_temperatures = platform.starting_temperatures
            self._audit = Audit(platform.audit)
        else:
            self.starting_temperatures = list()
            self.audit = dict()

        # Import data from a Results object serialised on disk.
        if results_file is not None:
            self.read_from_file(results_file)

    @property
    def audit(self):
        return self._audit

    @audit.setter
    def audit(self, audit_dict):
        self._audit = Audit(audit_dict)

    def init_from_config(self):
        """Scaffold dictionaries based on a given configuration.
        """
        # Initialise dictionaries based on config information.
        for vm_name, vm_info in self.config.VMS.items():
            for bmark, _ in self.config.BENCHMARKS.items():
                for variant in vm_info["variants"]:
                    key = ":".join((bmark, vm_name, variant))
                    self.data[key] = []
                    self.inst_data[key] = {}
                    self.eta_estimates[key] = []

    def read_from_file(self, results_file):
        """Initialise object from serialised file on disk.
        """
        with bz2.BZ2File(results_file, "rb") as f:
            results = json.loads(f.read())
            self.__dict__.update(results)
            # Ensure that self.audir and self.config have correct types.
            self.config = Config(None)
            self.config.read_from_string(results["config"])
            self.audit = results["audit"]

    def write_to_file(self):
        """Serialise object on disk."""

        debug("Writing results out to: %s" % self.filename)

        to_write = {
            "config": self.config.text,
            "data": self.data,
            "inst_data": self.inst_data,
            "audit": self.audit.audit,
            "reboots": self.reboots,
            "starting_temperatures": self.starting_temperatures,
            "eta_estimates": self.eta_estimates,
            "error_flag": self.error_flag,
        }
        with bz2.BZ2File(self.filename, "w") as f:
            f.write(json.dumps(to_write,
                               indent=1, sort_keys=True, encoding='utf-8'))

    def add_instrumentation_data(self, bench_key, inst_dct):
        """Record instrumentation data into results object."""

        for inst_key, v in inst_dct.iteritems():
            # keys in dict are arbitrary, so we may need to scaffold a new list
            if inst_key not in self.inst_data[bench_key]:
                self.inst_data[bench_key][inst_key] = []
            self.inst_data[bench_key][inst_key].append(v)

    def jobs_completed(self, key):
        """Return number of executions for which we have data for a given
        benchmark / vm / variant triplet.
        """
        return len(self.data[key])

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (self.config == other.config and
                self.data == other.data and
                self.audit == other.audit and
                self.reboots == other.reboots and
                self.starting_temperatures == other.starting_temperatures and
                self.eta_estimates == other.eta_estimates and
                self.error_flag == other.error_flag)

    def strip_results(self, key_spec):
        debug("Strip results: %s" % key_spec)

        spec_elems = key_spec.split(":")
        if len(spec_elems) != 3:
            fatal("malformed key spec: %s" % key_spec)

        new_data = self.data.copy()
        removed_keys = 0
        removed_execs = 0

        # We have to keep track of how many executions have run successfully so
        # that we can set self.reboots accordingly. It's not correct to simply
        # deduct one for each execution we remove, as the reboots value is one
        # higher due to the initial reboot. Bear in mind the user may strip
        # several result keys in succession, so counting the completed
        # executions is the only safe way.
        completed_execs = 0

        for key in self.data.iterkeys():
            key_elems = key.split(":")
            # deal with wildcards
            for i in xrange(3):
                if spec_elems[i] == "*":
                    key_elems[i] = "*"

            # decide whether to remove
            if key_elems == spec_elems:
                removed_keys += 1
                removed_execs += len(new_data[key])
                new_data[key] = []
                self.eta_estimates[key] = []
                info("Removed results for: %s" % key)
            else:
                completed_execs += len(new_data[key])

        self.data = new_data

        # If the results were collected with reboot mode, update reboots count
        if self.reboots != 0:
            self.reboots = completed_execs

        return removed_keys
