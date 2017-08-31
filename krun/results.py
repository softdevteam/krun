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

from krun.audit import Audit
from logging import debug
from krun.util import fatal, format_raw_exec_results

import bz2  # decent enough compression with Python 2.7 compatibility.
import json


class Results(object):
    """Results of a Krun benchmarking session.
    Can be serialised to disk.
    """

    # We use this to detect times where a results instance is loaded prior to a
    # process execution. This wouuld be bad, as the results can be big and
    # cause memory to fragment.
    ok_to_instantiate = False

    def __init__(self, config, platform, results_file=None):
        self.instantiation_check()

        self.config = config
        self.platform = platform

        # "bmark:vm:variant" -> [[e0i0, e0i1, ...], [e1i0, e1i1, ...], ...]
        self.wallclock_times = dict()  # wall-clock times

        # Secondary, per-core measurements
        # Structure as above, but lifted for N processor cores.
        # i.e. aperf_counts[core#][proc_exec#][in_proc_iter#]
        self.core_cycle_counts = dict()
        self.aperf_counts = dict()
        self.mperf_counts = dict()

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
            self.config_text = self.config.text
        if platform is not None:
            self._audit = Audit(platform.audit)
        else:
            self.audit = dict()

        # Import data from a Results object serialised on disk.
        if results_file is not None:
            self.read_from_file(results_file)

    def instantiation_check(self):
        if not Results.ok_to_instantiate:
            fatal("Results instance loaded prior to a process execution")

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
                    self.wallclock_times[key] = []
                    self.core_cycle_counts[key] = []
                    self.aperf_counts[key] = []
                    self.mperf_counts[key] = []
                    self.eta_estimates[key] = []

    def read_from_file(self, results_file):
        """Initialise object from serialised file on disk.
        """
        with bz2.BZ2File(results_file, "rb") as f:
            results = json.loads(f.read())
            config = results.pop("config")
            self.__dict__.update(results)
            # Ensure that self.audit and self.config have correct types.
            self.config_text = config
            if self.config is not None:
                self.config.check_config_consistency(config, results_file)
            self.audit = results["audit"]

    def integrity_check(self):
        """Check the results make sense"""

        num_cores = self.platform.num_per_core_measurements
        for key in self.wallclock_times.iterkeys():
            wct_len = len(self.wallclock_times[key])
            eta_len = len(self.eta_estimates[key])
            cycles_len = len(self.core_cycle_counts[key])
            aperf_len = len(self.aperf_counts[key])
            mperf_len = len(self.mperf_counts[key])

            if eta_len != wct_len:
                fatal("inconsistent etas length: %s: %d vs %d" % (key, eta_len, wct_len))

            if cycles_len != wct_len:
                fatal("inconsistent cycles length: %s: %d vs %d" % (key, cycles_len, wct_len))

            if aperf_len != wct_len:
                fatal("inconsistent aperf length: %s: %d vs %d" % (key, aperf_len, wct_len))

            if mperf_len != wct_len:
                fatal("inconsistent mperf length: %s: %d vs %d" % (key, mperf_len, wct_len))

            # Check the length of the different measurements match and that the
            # number of per-core measurements is consistent.
            for exec_idx in xrange(len(self.wallclock_times[key])):
                expect_num_iters = len(self.wallclock_times[key][exec_idx])

                cycles_num_cores = len(self.core_cycle_counts[key][exec_idx])
                if cycles_num_cores != self.platform.num_per_core_measurements:
                    fatal("wrong #cores in core_cycle_counts: %s[%d]: %d vs %d" %
                          (key, exec_idx, num_cores, cycles_num_cores))
                for core_idx, core in enumerate(self.core_cycle_counts[key][exec_idx]):
                    core_len = len(core)
                    if core_len != expect_num_iters:
                        fatal("inconsistent #iters in core_cycle_counts: "
                              "%s[%d][%d]. %d vs %d" %
                              (key, exec_idx, core_idx, core_len, expect_num_iters))

                aperf_num_cores = len(self.aperf_counts[key][exec_idx])
                if aperf_num_cores != self.platform.num_per_core_measurements:
                    fatal("wrong #cores in aperf_counts: %s[%d]: %d vs %d" %
                          (key, exec_idx, num_cores, aperf_num_cores))
                for core_idx, core in enumerate(self.aperf_counts[key][exec_idx]):
                    core_len = len(core)
                    if core_len != expect_num_iters:
                        fatal("inconsistent #iters in aperf_counts: "
                              "%s[%d][%d]. %d vs %d" %
                              (key, exec_idx, core_idx, core_len, expect_num_iters))

                mperf_num_cores = len(self.mperf_counts[key][exec_idx])
                if mperf_num_cores != self.platform.num_per_core_measurements:
                    fatal("wrong #cores in mperf_counts: %s[%d]: %d vs %d" %
                          (key, exec_idx, num_cores, mperf_num_cores))
                for core_idx, core in enumerate(self.mperf_counts[key][exec_idx]):
                    core_len = len(core)
                    if core_len != expect_num_iters:
                        fatal("inconsistent #iters in mperf_counts: "
                              "%s[%d][%d]. %d vs %d" %
                              (key, exec_idx, core_idx, core_len, expect_num_iters))

    def write_to_file(self):
        """Serialise object on disk."""

        debug("Writing results out to: %s" % self.filename)
        self.integrity_check()

        to_write = {
            "config": self.config.text,
            "wallclock_times": self.wallclock_times,
            "core_cycle_counts": self.core_cycle_counts,
            "aperf_counts": self.aperf_counts,
            "mperf_counts": self.mperf_counts,
            "audit": self.audit.audit,
            "eta_estimates": self.eta_estimates,
            "error_flag": self.error_flag,
        }
        with bz2.BZ2File(self.filename, "w") as f:
            f.write(json.dumps(to_write,
                               indent=1, sort_keys=True, encoding='utf-8'))

    def jobs_completed(self, key):
        """Return number of executions for which we have data for a given
        benchmark / vm / variant triplet.
        """
        return len(self.wallclock_times[key])

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return (self.config == other.config and
                self.wallclock_times == other.wallclock_times and
                self.core_cycle_counts == other.core_cycle_counts and
                self.aperf_counts == other.aperf_counts and
                self.mperf_counts == other.mperf_counts and
                self.audit == other.audit and
                self.eta_estimates == other.eta_estimates and
                self.error_flag == other.error_flag)

    def append_exec_measurements(self, key, measurements):
        """Unpacks a measurements dict into the Results instance"""

        # Consistently format monotonic time doubles
        wallclock_times = format_raw_exec_results(
            measurements["wallclock_times"])

        self.wallclock_times[key].append(wallclock_times)
        self.core_cycle_counts[key].append(measurements["core_cycle_counts"])
        self.aperf_counts[key].append(measurements["aperf_counts"])
        self.mperf_counts[key].append(measurements["mperf_counts"])

    def dump(self, what):
        if what == "config":
            return unicode(self.config_text)
        if what == "audit":
            return unicode(self.audit)
        return json.dumps(getattr(self, what),
                          sort_keys=True, indent=2)
