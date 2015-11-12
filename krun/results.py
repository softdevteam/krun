import bz2  # decent enough compression with Python 2.7 compatibility.
import json

import krun.util as util

class Results(object):
    """Results of a Krun benchmarking session.
    Can be serialised to disk.
    """
    def __init__(self, results_file=None, config_file=None):
        # Maps key to results:
        # "bmark:vm:variant" -> [[e0i0, e0i1, ...], [e1i0, e1i1, ...], ...]
        self.data = dict()
        self.audit = dict()
        self.config = u""  # FIXME: Should be a krun.config.Config object.
        self.reboots = 0
        # Record how long execs are taking so we can give the user a rough ETA.
        # Maps "bmark:vm:variant" -> [t_0, t_1, ...]
        self.etas = dict()
        self.starting_temperatures = list()
        # error_flag is flipped when a (non-fatal) error or warning occurs.
        # When Krun finishes and this flag is true, a message is printed,
        # thus prompting the user to investigate.
        self.error_flag = False
        if results_file is not None:
            self.read_from_file(results_file)
        if config_file is not None:
            self.init_from_config(config_file)

    def init_from_config(self, config_file):
        """Scaffold dictionaries based on a given configuration.
        """
        with open(config_file, "r") as fp:
            self.config = fp.read()
        config = util.read_config(config_file)
        # Initialise dictionaries based on config information.
        # FIXME! self.config should be an object.
        for vm_name, vm_info in config["VMS"].items():
            for bmark, _ in config["BENCHMARKS"].items():
                for variant in vm_info["variants"]:
                    key = ":".join((bmark, vm_name, variant))
                    if key in self.data:
                        continue
                    self.data[key] = [list() for _ in range(config["N_EXECUTIONS"])]
                    self.etas[key] = []

    def read_from_file(self, results_file):
        """Initialise object from serialised file on disk.
        """
        results = None
        with bz2.BZ2File(results_file, "rb") as f:
            results = json.loads(f.read())
        self.__dict__ = results

    def write_to_file(self, results_file):
        """Serialise object on disk.
        """
        with bz2.BZ2File(results_file, "w") as f:
            f.write(self.__repr__())

    def jobs_completed(self, key):
        """Return number of executions for which we have data for a given
        benchmark / vm / variant triplet.
        """
        return len(self.data[key])

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __repr__(self):
        return json.dumps(self.__dict__,
                          indent=1, sort_keys=True, encoding='utf-8')
