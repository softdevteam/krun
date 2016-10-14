import os.path
import pytest

from krun.config import Config
from krun.scheduler import ManifestManager

DEFAULT_MANIFEST = "krun.manifest"
TEST_DIR = os.path.abspath(os.path.dirname(__file__))

BLANK_EXAMPLE_MANIFEST = """eta_avail_idx=4
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


def _setup(filename, contents):
    ManifestManager.PATH = os.path.join(TEST_DIR, filename)
    assert ManifestManager.PATH == os.path.join(TEST_DIR, filename)
    with open(os.path.join(TEST_DIR, filename), "w") as fd:
        fd.write(contents)


def _tear_down():
    os.unlink(ManifestManager.PATH)
    ManifestManager.PATH = DEFAULT_MANIFEST
    assert ManifestManager.PATH == DEFAULT_MANIFEST


def test_parse_manifest():
    _setup("example_000.manifest", BLANK_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 21
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.skipped_keys == set()
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java","dummy:CPython:default-python",
        "nbody:CPython:default-python",]
    )
    _tear_down()


def test_parse_empty_manifest():
    _setup("example_000.manifest", "")
    with pytest.raises(AssertionError):
        _ = ManifestManager()
    _tear_down()


def test_parse_erroneous_manifest_001():
    _setup("example_000.manifest", """eta_avail_idx=4
keys
X dummy:Java:default-java""")
    with pytest.raises(AssertionError):
        _ = ManifestManager()
    _tear_down()


def test_parse_erroneous_manifest_002():
    _setup("example_000.manifest", """eta_aval_idx=4
keys
O dummy:Java:default-java""")
    with pytest.raises(AssertionError):
        _ = ManifestManager()
    _tear_down()


def test_parse_erroneous_manifest_003():
    _setup("example_000.manifest", """eta_avail_idx=4
keyz
O dummy:Java:default-java""")
    with pytest.raises(ValueError):
        _ = ManifestManager()
    _tear_down()


def test_parse_erroneous_manifest_004():
    _setup("example_000.manifest", """eta_avail_idx=4,
keys
O dummy:Java:default-java""")
    with pytest.raises(ValueError):
        _ = ManifestManager()
    _tear_down()


def test_parse_with_skips():
    _setup("example_skips.manifest", SKIPS_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 6
    assert manifest.next_exec_key == "dummy:CPython:default-python"
    assert manifest.next_exec_idx == 2
    assert manifest.next_exec_flag_offset == 73
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 1,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    assert manifest.skipped_keys == set(["dummy:Java:default-java",
                                        "nbody:Java:default-java"])
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java","dummy:CPython:default-python",
        "nbody:CPython:default-python",]
    )
    _tear_down()


def test_parse_with_all_skips():
    _setup("example_skips.manifest", SKIPS_ALL_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
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
    assert manifest.skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java","dummy:CPython:default-python",
        "nbody:CPython:default-python",])
    assert manifest.non_skipped_keys == set()
    _tear_down()


def test_parse_with_all_errors():
    _setup("example_errors.manifest", ERRORS_ALL_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
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
    assert manifest.skipped_keys == set()
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java","dummy:CPython:default-python",
        "nbody:CPython:default-python",])
    _tear_down()


def test_parse_with_skips_at_end():
    _setup("example_skips.manifest", SKIPS_END_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
    assert manifest.eta_avail_idx == 4
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 6
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 21
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 1,
        "nbody:CPython:default-python": 1,
    }
    assert manifest.skipped_keys == set(["dummy:CPython:default-python",
                                         "nbody:CPython:default-python",])
    assert manifest.non_skipped_keys == set(["dummy:Java:default-java",
        "nbody:Java:default-java","dummy:CPython:default-python",
        "nbody:CPython:default-python",]
    )
    _tear_down()


def test_get_total_in_proc_iters():
    _setup("example_000.manifest", BLANK_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    assert manifest.get_total_in_proc_iters(config) == 8 * 5  # Executions * iterations
    _tear_down()


def test_from_config0001():
    _setup("example_000.manifest", BLANK_EXAMPLE_MANIFEST)
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    manifest_from_config = ManifestManager.from_config(config)
    manifest = ManifestManager()
    assert manifest_from_config == manifest
    _tear_down()


def test_from_config_0002():
    config_path = os.path.join(TEST_DIR, "more_complicated.krun")
    config = Config(config_path)
    manifest = ManifestManager.from_config(config)
    assert manifest.total_num_execs == 90  # taking into account skips
    _tear_down()


def test_update_blank():
    _setup("example_blank.manifest", BLANK_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 21
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    # Benchmark completed.
    manifest.update("C")
    assert manifest.num_execs_left == 7
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "nbody:Java:default-java"
    assert manifest.next_exec_idx == 1
    assert manifest.next_exec_flag_offset == 47
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    # Benchmark failed.
    manifest.update("E")
    assert manifest.num_execs_left == 6
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:CPython:default-python"
    assert manifest.next_exec_idx == 2
    assert manifest.next_exec_flag_offset == 73
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 1,
        "nbody:Java:default-java": 1,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
    }
    _tear_down()


def test_update_to_completion():
    _setup("example_blank.manifest", BLANK_EXAMPLE_MANIFEST)
    manifest = ManifestManager()
    assert manifest.num_execs_left == 8
    assert manifest.total_num_execs == 8
    assert manifest.next_exec_key == "dummy:Java:default-java"
    assert manifest.next_exec_idx == 0
    assert manifest.next_exec_flag_offset == 21
    assert manifest.outstanding_exec_counts == {
        "dummy:Java:default-java": 2,
        "nbody:Java:default-java": 2,
        "dummy:CPython:default-python": 2,
        "nbody:CPython:default-python": 2,
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
    _tear_down()
