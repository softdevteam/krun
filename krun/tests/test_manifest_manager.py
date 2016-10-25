import os.path
import pytest

from krun.config import Config
from krun.scheduler import ManifestManager
from krun.util import FatalKrunError

DEFAULT_MANIFEST = "krun.manifest"
TEST_DIR = os.path.abspath(os.path.dirname(__file__))

BLANK_EXAMPLE_MANIFEST = """eta_avail_idx=4
num_mails_sent=0000
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


def _setup(contents):
    class FakeConfig(object):
        filename = os.path.join(TEST_DIR, "manifest_tests.krun")
    config = FakeConfig()

    with open(ManifestManager.get_filename(config), "w") as fh:
        fh.write(contents)
    return ManifestManager(config)


def _tear_down(filename):
    if os.path.exists(filename):
        os.unlink(filename)


def test_parse_manifest():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 41
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
    _tear_down(manifest.path)


def test_parse_empty_manifest():
    with pytest.raises(AssertionError):
        _setup("")
    _tear_down("example_000.manifest")


def test_parse_erroneous_manifest_001():
    with pytest.raises(AssertionError):
        _setup("""eta_avail_idx=4
keys
X dummy:Java:default-java""")
    _tear_down("example_000.manifest")


def test_parse_erroneous_manifest_002():
    with pytest.raises(FatalKrunError):
        _setup("""bob=4
keys
O dummy:Java:default-java""")
    _tear_down("example_000.manifest")


def test_parse_erroneous_manifest_003():
    with pytest.raises(ValueError):
        _setup("""eta_avail_idx=4
num_mails_sent=0000
keyz
O dummy:Java:default-java""")
    _tear_down("example_000.manifest")


def test_parse_erroneous_manifest_004():
    with pytest.raises(ValueError):
        manifest = _setup("""eta_avail_idx=4,
num_mails_sent=0000
keys
O dummy:Java:default-java""")
    _tear_down("example_000.manifest")


def test_parse_with_skips():
    manifest = _setup(SKIPS_EXAMPLE_MANIFEST)
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 6
    assert manifest.next_exec_key == "dummy:CPython:default-python"
    assert manifest.next_exec_idx == 2
    assert manifest.next_exec_flag_offset == 93
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
    assert manifest.next_exec_flag_offset == 41
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


def test_write_new_manifest0001():
    _setup(BLANK_EXAMPLE_MANIFEST)
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    manifest1 = ManifestManager(config, new_file=True)
    manifest2 = ManifestManager(config)  # reads the file in from the last line
    assert manifest1 == manifest2
    _tear_down(manifest2.path)


def test_write_new_manifest0002():
    manifest_path = "example_000.manifest"
    config_path = os.path.join(TEST_DIR, "more_complicated.krun")
    config = Config(config_path)
    manifest = ManifestManager(config, new_file=True)
    assert manifest.total_num_execs == 90  # taking into account skips
    _tear_down(manifest.path)


def test_update_blank():
    manifest = _setup(BLANK_EXAMPLE_MANIFEST)
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 41
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
    assert manifest.next_exec_flag_offset == 67
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
    assert manifest.next_exec_flag_offset == 93
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
    assert manifest.next_exec_flag_offset == 41
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
    assert manifest.next_exec_flag_offset == 207
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
