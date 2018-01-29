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
import pytest

from krun.config import Config
from krun.scheduler import ManifestManager
from krun.util import FatalKrunError
from krun.tests.mocks import MockPlatform, mock_platform

DEFAULT_MANIFEST = "krun.manifest"
TEST_DIR = os.path.abspath(os.path.dirname(__file__))

BLANK_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
O dummy:Java:default-java
O nbody:Java:default-java
O dummy:CPython:default-python
O nbody:CPython:default-python
O dummy:Java:default-java
O nbody:Java:default-java
O dummy:CPython:default-python
O nbody:CPython:default-python
"""

SKIPS_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
S dummy:Java:default-java
S nbody:Java:default-java
O dummy:CPython:default-python
O nbody:CPython:default-python
O dummy:Java:default-java
O nbody:Java:default-java
O dummy:CPython:default-python
O nbody:CPython:default-python
"""

SKIPS_END_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
O dummy:Java:default-java
O nbody:Java:default-java
O dummy:CPython:default-python
O nbody:CPython:default-python
O dummy:Java:default-java
O nbody:Java:default-java
S dummy:CPython:default-python
S nbody:CPython:default-python
"""

SKIPS_ALL_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
S dummy:Java:default-java
S nbody:Java:default-java
S dummy:CPython:default-python
S nbody:CPython:default-python
S dummy:Java:default-java
S nbody:Java:default-java
S dummy:CPython:default-python
S nbody:CPython:default-python
"""

ERRORS_ALL_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
E dummy:Java:default-java
E nbody:Java:default-java
E dummy:CPython:default-python
E nbody:CPython:default-python
E dummy:Java:default-java
E nbody:Java:default-java
E dummy:CPython:default-python
E nbody:CPython:default-python
"""

IRREGULAR_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
E dummy:Java:default-java
C nbody:Java:default-java
C dummy:CPython:default-python
S nbody:CPython:default-python
C dummy:Java:default-java
S nbody:Java:default-java
O dummy:CPython:default-python
E nbody:CPython:default-python
"""

# num_mails_sent is missing
MISSING_HEADER_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_reboots=00000000
keys
E dummy:Java:default-java
C nbody:Java:default-java
C dummy:CPython:default-python
S nbody:CPython:default-python
C dummy:Java:default-java
S nbody:Java:default-java
O dummy:CPython:default-python
E nbody:CPython:default-python
"""

THIRD_KEY_REP_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
num_reboots=00000000
keys
E dummy:Java:default-java
C nbody:Java:default-java
C dummy:CPython:default-python
S nbody:CPython:default-python
C dummy:Java:default-java
S nbody:Java:default-java
C dummy:CPython:default-python
E nbody:CPython:default-python
C dummy:Java:default-java
S nbody:Java:default-java
O dummy:CPython:default-python
E nbody:CPython:default-python
"""

def _setup(contents):
    class FakeConfig(object):
        filename = os.path.join(TEST_DIR, "manifest_tests.krun")
    config = FakeConfig()

    with open(ManifestManager.get_filename(config), "w") as fh:
        fh.write(contents)
    return ManifestManager(config, MockPlatform(None, config))


def _tear_down(filename):
    if os.path.exists(filename):
        os.unlink(filename)
    else:
        assert(False)


def test_parse_manifest():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 62
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.skipped_keys == set()
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java", "dummy:CPython:default-python",
        "nbody:CPython:default-python",]
    )
    assert manifest.num_reboots == 0
    assert manifest.num_reboots_offset == 48
    assert manifest.num_mails_sent == 0
    assert manifest.num_mails_sent_offset == 31
    _tear_down(manifest.path)


def test_parse_empty_manifest():
    with pytest.raises(AssertionError):
        _setup("")
    _tear_down(os.path.join("krun", "tests", "manifest_tests.manifest"))


def test_parse_erroneous_manifest_001():
    with pytest.raises(AssertionError):
        _setup("""eta_avail_idx=4
keys
X dummy:Java:default-java""")
    _tear_down(os.path.join("krun", "tests", "manifest_tests.manifest"))


def test_parse_erroneous_manifest_002():
    with pytest.raises(FatalKrunError):
        _setup("""bob=4
keys
O dummy:Java:default-java""")
    _tear_down(os.path.join("krun", "tests", "manifest_tests.manifest"))


def test_parse_erroneous_manifest_003():
    with pytest.raises(ValueError):
        _setup("""eta_avail_idx=4
num_mails_sent=0000
keyz
O dummy:Java:default-java""")
    _tear_down(os.path.join("krun", "tests", "manifest_tests.manifest"))


def test_parse_erroneous_manifest_004():
    with pytest.raises(ValueError):
        manifest = _setup("""eta_avail_idx=4,
num_mails_sent=0000
keys
O dummy:Java:default-java""")
    _tear_down(os.path.join("krun", "tests", "manifest_tests.manifest"))


def test_parse_with_skips():
    manifest = _setup(SKIPS_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 6
    assert manifest.next_exec_key == "dummy:CPython:default-python"
    assert manifest.next_exec_idx == 2
    assert manifest.next_exec_flag_offset == 114
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 1,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.skipped_keys == set(["dummy:Java:default-java",
                                        "nbody:Java:default-java"])
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java", "dummy:CPython:default-python",
        "nbody:CPython:default-python",]
    )
    _tear_down(manifest.path)


def test_parse_with_all_skips():
    manifest = _setup(SKIPS_ALL_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 0
    assert manifest.total_num_execs == 0
    assert manifest.next_exec_key == None
    assert manifest.next_exec_idx == -1
    assert manifest.next_exec_flag_offset == None
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java", "dummy:CPython:default-python",
        "nbody:CPython:default-python",])
    assert manifest.non_skipped_keys == set()
    _tear_down(manifest.path)


def test_parse_with_all_errors():
    manifest = _setup(ERRORS_ALL_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 0
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == None
    assert manifest.next_exec_idx == -1
    assert manifest.next_exec_flag_offset == None
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.skipped_keys == set()
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java", "dummy:CPython:default-python",
        "nbody:CPython:default-python",])
    _tear_down(manifest.path)


def test_parse_with_skips_at_end():
    manifest = _setup(SKIPS_END_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 6
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 62
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 1,
        "nbody:CPython:default-python": 1,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.skipped_keys == set(["dummy:CPython:default-python",
                                         "nbody:CPython:default-python",])
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java", "dummy:CPython:default-python",
        "nbody:CPython:default-python",]
    )
    _tear_down(manifest.path)


def test_get_total_in_proc_iters():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    assert manifest.get_total_in_proc_iters(config) == 8 * 5  # Executions * iterations
    _tear_down(manifest.path)


def test_write_new_manifest0001(mock_platform):
    _setup(BLANK_EXAMPLE_MANIFEST)
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    manifest1 = ManifestManager(config, mock_platform, new_file=True)
    manifest2 = ManifestManager(config, mock_platform)  # reads the file in from the last line
    assert manifest1 == manifest2
    _tear_down(manifest2.path)


def test_write_new_manifest0002(mock_platform):
    manifest_path = "example_000.manifest"
    config_path = os.path.join(TEST_DIR, "more_complicated.krun")
    config = Config(config_path)
    manifest = ManifestManager(config, mock_platform, new_file=True)
    assert manifest.total_num_execs == 90  # taking into account skips
    _tear_down(manifest.path)


def test_update_blank():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 62
    assert manifest.num_mails_sent_offset == 31
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    # Benchmark completed.
    manifest.update("C")
    assert manifest.num_execs_left == 7
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "nbody:Java:default-java"
    assert manifest.next_exec_idx == 1
    assert manifest.next_exec_flag_offset == 88
    assert manifest.num_mails_sent_offset == 31
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    # Benchmark failed.
    manifest.update("E")
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:CPython:default-python"
    assert manifest.next_exec_idx == 2
    assert manifest.next_exec_flag_offset == 114
    assert manifest.num_mails_sent_offset == 31
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 1,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 1,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    _tear_down(manifest.path)


def test_update_to_completion():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 62
    assert manifest.num_mails_sent_offset == 31
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    # Complete each benchmark.
    for completed in xrange(1, 9):
        manifest.update("C")
        assert manifest.num_execs_left == 8 - completed
        assert manifest.total_num_execs == 8
    assert manifest.next_exec_idx == -1
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 0,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    _tear_down(manifest.path)

def test_irregular_manifest():
    manifest = _setup(IRREGULAR_EXAMPLE_MANIFEST)
    assert manifest.num_execs_left == 1
    assert manifest.total_num_execs == 6
    assert manifest.next_exec_key == "dummy:CPython:default-python"
    assert manifest.next_exec_idx == 6
    assert manifest.next_exec_flag_offset == 228
    assert manifest.num_mails_sent_offset == 31
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 0,
        "nbody:Java:default-java": 0,
        "dummy:CPython:default-python": 1,
        "nbody:CPython:default-python": 0,
    }
    assert manifest.completed_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 1,
        "dummy:CPython:default-python": 1,
        "nbody:CPython:default-python": 1,
    }
    _tear_down(manifest.path)

def test_update_num_mails_sent0001():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.num_mails_sent == 0
    manifest.update_num_mails_sent()
    assert manifest.num_mails_sent == 1
    manifest.update_num_mails_sent()
    manifest.update_num_mails_sent()
    assert manifest.num_mails_sent == 3
    _tear_down(manifest.path)

def test_update_num_mails_sent0002():
    """Tests the overflow case"""

    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    manifest.num_mails_sent = manifest.num_mails_maxout
    with pytest.raises(AssertionError):
        manifest.update_num_mails_sent()
    _tear_down(manifest.path)


def test_update_num_reboots0001():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.num_reboots == 0
    manifest.update_num_reboots()
    assert manifest.num_reboots == 1
    manifest.update_num_reboots()
    manifest.update_num_reboots()
    assert manifest.num_reboots == 3
    _tear_down(manifest.path)


def test_update_num_reboots0002():
    """Tests the overflow case"""

    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    manifest.num_reboots = manifest.num_reboots_maxout
    with pytest.raises(AssertionError):
        manifest.update_num_reboots()
    _tear_down(manifest.path)

def test_missing_header_manifest0001():
    with pytest.raises(AssertionError):
        manifest = _setup(MISSING_HEADER_EXAMPLE_MANIFEST)
    _tear_down(os.path.join("krun", "tests", "manifest_tests.manifest"))


def test_next_exec_key_index0001():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.next_exec_key_index() == 0
    _tear_down(manifest.path)


def test_next_exec_key_index0002():
    manifest = _setup(SKIPS_EXAMPLE_MANIFEST)
    assert manifest.next_exec_key_index() == 0
    _tear_down(manifest.path)


def test_next_exec_key_index0003():
    manifest = _setup(ERRORS_ALL_EXAMPLE_MANIFEST)
    with pytest.raises(FatalKrunError) as e:
        manifest.next_exec_key_index()
    assert "Manifest ended unexpectedly" in str(e)
    _tear_down(manifest.path)


def test_next_exec_key_index0004():
    manifest = _setup(THIRD_KEY_REP_EXAMPLE_MANIFEST)
    assert manifest.next_exec_key_index() == 2
    _tear_down(manifest.path)
