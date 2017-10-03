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

from krun import LOGFILE_FILENAME_TIME_FORMAT
from krun.config import Config
from krun.env import EnvChangeAppend
from krun.util import FatalKrunError

import os
import pytest
import time
import sys
import krun.platform
from distutils.spawn import find_executable


JAVA = find_executable("java")
from krun.tests import TEST_DIR

def touch(fname):
    with open(fname, 'a'):
        os.utime(fname, None)


def test_str():
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)
    assert config.text == str(config)

def test_eq():
    path = os.path.join(TEST_DIR, "example.krun")
    example_config = Config(path)
    assert example_config == example_config
    assert not example_config == None
    assert not example_config == Config("krun/tests/quick.krun")


def test_log_filename0001():
    path = os.path.join(TEST_DIR, "example.krun")
    example_config = Config(path)
    expect_path = os.path.join(TEST_DIR, "example.log")
    assert example_config.log_filename(False) == expect_path


def test_read_config_from_file():
    path = os.path.join(TEST_DIR, "example.krun")
    config0 = Config(path)
    config1 = Config(None)
    config1.read_from_file(path)
    assert config0 == config1


def test_check_config_consistency():
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)
    with open(path) as fp:
        config_string = fp.read()
    config.check_config_consistency(config_string, "fakefilename")

def test_check_config_consistency_fails():
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)
    with open(path) as fp:
        config_string = fp.read()
    with pytest.raises(Exception) as excinfo:
        config.check_config_consistency(config_string + "\n# different config!",
                                        "fakefilename")
    print excinfo.value.message
    assert "+# different config!" in excinfo.value.message

@pytest.mark.skipif(JAVA is None, reason="No Java found")
def test_config_init():
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)
    assert config is not None
    assert config.BENCHMARKS == {"dummy": 1000, "nbody": 1000}
    assert config.N_EXECUTIONS == 2
    assert config.SKIP == []
    assert config.MAIL_TO == []
    assert config.ITERATIONS_ALL_VMS == 5
    assert config.HEAP_LIMIT == 2097152


def test_read_corrupt_config():
    path = os.path.join(TEST_DIR, "corrupt.krun")
    with pytest.raises(Exception):
        Config(path)


def test_results_filename():
    example = os.path.join(TEST_DIR, "example.krun")
    touch(example)
    example_config = Config(example)
    # not exact match due to absolute path
    assert example_config.results_filename().endswith("example_results.json.bz2")


def test_skip0001():
    path = os.path.join(TEST_DIR, "skips.krun")
    config = Config(path)
    expected = ["*:PyPy:*",
                "*:CPython:*",
                "*:Hotspot:*",
                "*:Graal:*",
                "*:LuaJIT:*",
                "*:HHVM:*",
                "*:TruffleRuby:*",
                "*:V8:*",
                ]
    for triplet in expected:
        assert config.should_skip(triplet)
    assert config.should_skip("nbody:HHVM:default-php")
    assert not config.should_skip("nbody:MYVM:default-php")


def test_skip0002():
    config = Config()
    config.SKIP = ["mybench:CPython:default-python"]

    assert config.should_skip("mybench:CPython:default-python")
    assert not config.should_skip("myotherbench:CPython:default-python")
    assert not config.should_skip("mybench:PyPy:default-python")
    assert not config.should_skip("mybench:CPython:special-python")


def test_skip0003():
    config = Config()
    config.SKIP = ["*:CPython:default-python"]

    assert config.should_skip("mybench:CPython:default-python")
    assert config.should_skip("myotherbench:CPython:default-python")
    assert not config.should_skip("mybench:PyPy:default-python")
    assert not config.should_skip("mybench:CPython:special-python")


def test_skip0004():
    config = Config()
    config.SKIP = ["mybench:*:default-python"]

    assert config.should_skip("mybench:CPython:default-python")
    assert not config.should_skip("myotherbench:CPython:default-python")
    assert config.should_skip("mybench:PyPy:default-python")
    assert not config.should_skip("mybench:CPython:special-python")

def test_skip0005():
    config = Config()
    config.SKIP = ["mybench:CPython:*"]

    assert config.should_skip("mybench:CPython:default-python")
    assert not config.should_skip("myotherbench:CPython:default-python")
    assert not config.should_skip("mybench:PyPy:default-python")
    assert config.should_skip("mybench:CPython:special-python")


def test_skip0006():
    config = Config()
    config.SKIP = ["*:*:*"]

    assert config.should_skip("mybench:CPython:default-python")
    assert config.should_skip("myotherbench:CPython:default-python")
    assert config.should_skip("mybench:PyPy:default-python")
    assert config.should_skip("mybench:CPython:special-python")


def test_skip0007():
    config = Config()

    with pytest.raises(ValueError) as e:
        config.should_skip("wobble")

    assert e.value.message == "bad benchmark key: wobble"

def test_skip0008():
    config = Config()
    config.SKIP = ["*:SomeVM:*", "fasta:TruffleRuby:default-ruby"]

    assert config.should_skip("fasta:TruffleRuby:default-ruby")

def test_skip0009():
    config = Config()
    config.SKIP = ["*:SomeVM:*",
                   "fasta:TruffleRuby:default-ruby",
                   "bench:*:*",
                   "bench:vm:skipvariant",
                   "*:*:skipvariant",
                   ]

    assert config.should_skip("fasta:TruffleRuby:default-ruby")
    assert not config.should_skip("fasta:TruffleRuby:default-ruby2")
    assert config.should_skip("bench:lala:hihi")
    assert config.should_skip("bench:lala:hihi2")
    assert not config.should_skip("bench1:lala:hihi")
    assert config.should_skip("bench1:lala:skipvariant")
    assert config.should_skip("bench1:lala2:skipvariant")

def test_skip0010():
    config = Config()
    config.SKIP = ["*:SomeVM:*",
                   "fasta:TruffleRuby:default-ruby",
                   "bench:*:*",
                   "bench:vm:skipvariant",
                   "*:*:skipvariant",
                   "*:*:*",  # everything should be skipped due to this
                   ]

    import uuid
    def rand_str():
        return uuid.uuid4().hex

    for i in xrange(25):
        key = "%s:%s:%s" % tuple([rand_str() for x in xrange(3)])
        assert config.should_skip(key)

def test_temp_read_pause0001():
    config = Config()
    assert config.TEMP_READ_PAUSE == 60  # default

def test_temp_read_pause0002():
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    assert config.TEMP_READ_PAUSE == 1


def test_user_env0001():
    config = Config(os.path.join(TEST_DIR, "env.krun"))
    vm_def = config.VMS["CPython"]["vm_def"]

    env = {}
    vm_def.apply_env_changes([], env)
    assert env == {
        'ANOTHER_ENV': 'arbitrary_user_val',
        'LD_LIBRARY_PATH': '/wibble/lib',
    }


def test_user_env0002():
    config = Config(os.path.join(TEST_DIR, "env.krun"))
    vm_def = config.VMS["CPython"]["vm_def"]

    env = {"LD_LIBRARY_PATH": "zzz"}
    vm_def.apply_env_changes([], env)
    assert env == {
        'ANOTHER_ENV': 'arbitrary_user_val',
        'LD_LIBRARY_PATH': 'zzz:/wibble/lib',
    }


def test_user_env0003():
    config = Config(os.path.join(TEST_DIR, "env.krun"))
    vm_def = config.VMS["CPython"]["vm_def"]

    env = {"LD_LIBRARY_PATH": "zzz"}

    bench_env_changes = [EnvChangeAppend("LD_LIBRARY_PATH", "abc")]
    vm_def.apply_env_changes(bench_env_changes, env)
    assert env == {
        'ANOTHER_ENV': 'arbitrary_user_val',
        'LD_LIBRARY_PATH': 'zzz:/wibble/lib:abc',
    }

def test_user_env0004():
    """Interesting case as PyPy forces a lib path at the VM level"""

    config = Config(os.path.join(TEST_DIR, "env.krun"))
    vm_def = config.VMS["PyPy"]["vm_def"]

    env = {}

    vm_def.apply_env_changes([], env)
    # Expect the user's env to come first
    assert env == {
        'ANOTHER_ENV': 'arbitrary_user_val',
        'LD_LIBRARY_PATH': '/wibble/lib:/opt/pypy/pypy/goal',
    }

def test_space_in_vm_name0001():
    path = os.path.join(TEST_DIR, "space_in_vm_name.krun")
    with pytest.raises(FatalKrunError) as e:
        config = Config(path)
    assert "VM names must not contain spaces" in str(e)


def test_space_in_benchmark_name0001():
    path = os.path.join(TEST_DIR, "space_in_benchmark_name.krun")
    with pytest.raises(FatalKrunError) as e:
        config = Config(path)
    assert "Benchmark names must not contain spaces" in str(e)


def test_space_in_variant_name0001():
    path = os.path.join(TEST_DIR, "space_in_variant_name.krun")
    with pytest.raises(FatalKrunError) as e:
        config = Config(path)
    assert "Variant names must not contain spaces" in str(e)


def test_custom_dmesg_whitelist0001(monkeypatch):
    """Test a config file that appends two patterns to the default whitelist"""

    path = os.path.join(TEST_DIR, "custom_dmesg_whitelist0001.krun")
    config = Config(path)
    platform = krun.platform.detect_platform(None, config)
    patterns = [p.pattern for p in platform.get_dmesg_whitelist()]
    assert patterns == platform.default_dmesg_whitelist() + \
        ["^custom1*", "^.custom2$"]


def test_custom_dmesg_whitelist0002(monkeypatch):
    """Test a config file that replaces entirely the dmesg whitelist"""

    path = os.path.join(TEST_DIR, "custom_dmesg_whitelist0002.krun")
    config = Config(path)
    platform = krun.platform.detect_platform(None, config)
    patterns = [p.pattern for p in platform.get_dmesg_whitelist()]
    assert patterns == ["^.no+", "^defaults", "^here+"]


def test_custom_dmesg_whitelist0003(monkeypatch):
    """Test a config file that uses no custom whitelist"""

    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)
    platform = krun.platform.detect_platform(None, config)
    patterns = [p.pattern for p in platform.get_dmesg_whitelist()]
    assert patterns == platform.default_dmesg_whitelist()
