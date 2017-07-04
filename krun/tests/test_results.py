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

from krun.config import Config
from krun.results import Results
from krun.tests import BaseKrunTest
from krun.util import FatalKrunError

import os
import pytest

TEST_DIR = os.path.abspath(os.path.dirname(__file__))


@pytest.fixture
def no_results_instantiation_check(monkeypatch):
    monkeypatch.setattr(Results, 'instantiation_check', lambda self: None)


@pytest.fixture
def fake_results(mock_platform, no_results_instantiation_check):
    results = Results(None, mock_platform)
    mock_platform.num_cpus = 2
    mock_platform.num_per_core_measurements = 2

    results.eta_estimates = {"bench:vm:variant": [1., 1.]}
    results.wallclock_times = {"bench:vm:variant": [[2., 2.], [2., 2.]]}
    results.core_cycle_counts = {"bench:vm:variant":
                                 [[[3., 3.], [3., 3.,]], [[3., 3.], [3., 3.]]]}
    results.aperf_counts = {"bench:vm:variant":
                            [[[4., 4.], [4., 4.,]], [[4., 4.], [4., 4.]]]}
    results.mperf_counts = {"bench:vm:variant":
                            [[[5., 5.], [5., 5.,]], [[5., 5.], [5., 5.]]]}
    return results


class TestResults(BaseKrunTest):
    """Test the results data structure and file."""

    def test_eq(self, mock_platform, no_results_instantiation_check):
        results = Results(None, None,
                          results_file="krun/tests/quick_results.json.bz2")
        assert results == results
        assert not results == None
        assert not results == \
            Results(Config("krun/tests/example.krun"), mock_platform)


    def test_dump_config(self, no_results_instantiation_check):
        """Simulates krun.py --dump-config RESULTS_FILE.json.bz2
        """

        res_path = os.path.join(TEST_DIR, "quick_results.json.bz2")
        conf_path = os.path.join(TEST_DIR, "quick.krun")
        results = Results(None, None, results_file=res_path)
        with open(conf_path) as fp:
            config = fp.read()
            assert config == results.dump("config")


    def test_read_results_from_disk(self, no_results_instantiation_check):
        config = Config("krun/tests/quick.krun")
        results = Results(config, None,
                          results_file="krun/tests/quick_results.json.bz2")
        expected = {u'nbody:CPython:default-python': [[0.022256]],
                    u'dummy:CPython:default-python': [[1.005115]],
                    u'nbody:Java:default-java': [[26.002632]],
                    u'dummy:Java:default-java': [[1.000941]]}
        assert results.config == config
        assert results.audit[u'uname'] == u'Linux'
        assert results.audit[u'debian_version'] == u'jessie/sid'
        assert results.wallclock_times == expected
        assert results.starting_temperatures == {"x": 3333, "y": 4444}
        assert results.eta_estimates == \
            {
                u'nbody:CPython:default-python': [0.022256],
                u'dummy:CPython:default-python': [1.005115],
                u'nbody:Java:default-java': [26.002632],
                u'dummy:Java:default-java': [1.000941]
            }


    def test_write_results_to_disk(self, mock_platform,
                                   no_results_instantiation_check):
        config = Config("krun/tests/example.krun")
        mock_platform.num_cpus = 4
        mock_platform.num_per_core_measurements = mock_platform.num_cpus
        out_file = "krun/tests/example_results.json.bz2"
        results0 = Results(config, mock_platform)
        results0.audit = dict()
        results0.starting_temperatures = [4355, 9879]
        results0.wallclock_times = {u"dummy:Java:default-java": [[1.000726]]}
        results0.eta_estimates = {u"dummy:Java:default-java": [1.1]}
        results0.core_cycle_counts = {u"dummy:Java:default-java": [[[2], [3], [4], [5]]]}
        results0.aperf_counts = {u"dummy:Java:default-java": [[[3], [4], [5], [6]]]}
        results0.mperf_counts = {u"dummy:Java:default-java": [[[4], [5], [6], [7]]]}
        results0.reboots = 5
        results0.error_flag = False
        results0.write_to_file()
        results1 = Results(config, None, results_file=out_file)
        assert results0 == results1
        # Clean-up generated file.
        os.unlink(out_file)

    def test_integrity_check_results0001(self, fake_results):
        """ETAs don't exist for all jobs for which there is iterations data"""

        fake_results.integrity_check()

    def test_integrity_check_results0002(self, fake_results, caplog,
                                         no_results_instantiation_check):
        # remove some eta info
        fake_results.eta_estimates["bench:vm:variant"].pop()
        with pytest.raises(FatalKrunError):
            fake_results.integrity_check()

        expect = "inconsistent etas length: bench:vm:variant: 1 vs 2"
        assert expect in caplog.text()

    def test_integrity_check_results0003(self, fake_results, caplog):
        # remove a per-core measurement
        fake_results.core_cycle_counts["bench:vm:variant"].pop()
        with pytest.raises(FatalKrunError):
            fake_results.integrity_check()

        expect = "inconsistent cycles length: bench:vm:variant: 1 vs 2"
        assert expect in caplog.text()

    def test_integrity_check_results0004(self, fake_results, caplog):
        # remove a core from a per-core measurement
        fake_results.core_cycle_counts["bench:vm:variant"][0].pop()
        with pytest.raises(FatalKrunError):
            fake_results.integrity_check()

        expect = "wrong #cores in core_cycle_counts: bench:vm:variant[0]: 2 vs 1"
        assert expect in caplog.text()

    def test_integrity_check_results0005(self, fake_results, caplog):
        # remove an in-proc iteration from a per-core measurement
        fake_results.core_cycle_counts["bench:vm:variant"][0][0].pop()
        with pytest.raises(FatalKrunError):
            fake_results.integrity_check()

        expect = "inconsistent #iters in core_cycle_counts: bench:vm:variant[0][0]. 1 vs 2"
        assert expect in caplog.text()
