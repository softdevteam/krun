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

import sys
import os
from tempfile import NamedTemporaryFile
import pytest
import json
from StringIO import StringIO
from krun.vm_defs import (PythonVMDef, PyPyVMDef, JavaVMDef)
from krun.config import Config
from distutils.spawn import find_executable
from krun.env import EnvChange
from krun.tests.mocks import MockPlatform
from krun.tests import BaseKrunTest
from krun import EntryPoint
from krun import util


class TestVMDef(BaseKrunTest):
    """Test stuff in VM definitions"""

    def test_make_wrapper_script0001(self, mock_platform):
        args = ["arg1", "arg2", "arg3"]
        heap_lim_k = 1024 * 1024 * 1024  # 1GiB
        stack_lim_k = 8192
        dash = find_executable("dash")
        assert dash is not None
        vmdef = PythonVMDef("python2.7")
        vmdef.set_platform(mock_platform)

        wrapper_filename, envlog_filename = vmdef.make_wrapper_script(
            args, heap_lim_k, stack_lim_k)
        expect = [
            '#!%s' % dash,
            'ENVLOG=`env`',
            'ulimit -d %s || exit $?' % heap_lim_k,
            'ulimit -s %s || exit $?' % stack_lim_k,
            'arg1 arg2 arg3',
            'echo "${ENVLOG}" > %s' % envlog_filename,
            'exit $?'
        ]

        with open(wrapper_filename) as fh:
            got = fh.read().splitlines()

        util.del_envlog_tempfile(envlog_filename, mock_platform)
        assert expect == got

    def test_env_ctor0001(self):
        vm = PythonVMDef("python2.7", env={"MYENV": "xyz"})

        assert len(vm.common_env_changes) == 1

        ec = vm.common_env_changes[0]
        assert ec.var == "MYENV"
        assert ec.val == "xyz"

    def test_env_ctor0002(self):
        vm = PyPyVMDef("/bin/pypy", env={"LD_LIBRARY_PATH": "/path/to/happiness"})

        assert len(vm.common_env_changes) == 2

        ec1 = vm.common_env_changes[0]
        assert ec1.var == "LD_LIBRARY_PATH"
        assert ec1.val == "/path/to/happiness"

        ec2 = vm.common_env_changes[1]
        assert ec2.var == "LD_LIBRARY_PATH"
        assert ec2.val == "/bin"

        env = {}
        EnvChange.apply_all(vm.common_env_changes, env)
        assert env["LD_LIBRARY_PATH"] == '/path/to/happiness:/bin'

    def test_sync_disks0001(self, monkeypatch):
        """Check disk sync method is called"""

        config = Config()
        platform = MockPlatform(None, config)
        ep = EntryPoint("test")
        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)

        sync_called = [False]
        def fake_sync_disks():
            sync_called[0] = True
        monkeypatch.setattr(platform, "sync_disks", fake_sync_disks)

        def fake_run_exec_popen(args, stderr_file=None):
            return "[1]", "", 0  # stdout, stderr, exit_code
        monkeypatch.setattr(vm_def, "_run_exec_popen", fake_run_exec_popen)

        vm_def.run_exec(ep, 1, 1, 1, 1, "test:dummyvm:default", 0)
        assert sync_called == [True]

    def test_sync_disks0002(self, monkeypatch):
        """We throw away the results from sanity checks, so there's no need to
        sync disks (and wait)."""

        stdout = json.dumps({
            "wallclock_times": [123.4],
            "core_cycle_counts": [[1], [2], [3], [4]],
            "aperf_counts": [[5], [6], [7], [8]],
            "mperf_counts": [[9], [10], [11], [12]],
        })

        config = Config()
        platform = MockPlatform(None, config)
        ep = EntryPoint("test")
        vm_def = PythonVMDef('/dummy/bin/python')

        sync_called = [False]
        def fake_sync_disks():
            sync_called[0] = True
        monkeypatch.setattr(platform, "sync_disks", fake_sync_disks)

        def fake_run_exec_popen(args, stderr_file=None):
            return stdout, "", 0  # stdout, stderr, exit_code

        monkeypatch.setattr(vm_def, "_run_exec_popen", fake_run_exec_popen)

        util.spawn_sanity_check(platform, ep, vm_def, "test")
        assert sync_called == [False]

    def test_run_exec_popen0001(self, monkeypatch):
        """Check normal operation of _run_exec_popen()"""

        config = Config()
        platform = MockPlatform(None, config)
        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)

        args = [sys.executable, "-c",
                "import sys; sys.stdout.write('STDOUT'); sys.stderr.write('STDERR')"]
        out, err, rv = vm_def._run_exec_popen(args)

        assert err == "STDERR"
        assert out == "STDOUT"
        assert rv == 0

    def test_run_exec_popen0002(self, monkeypatch):
        """Check that writing stderr to a file works. Used for instrumentation"""

        config = Config()
        platform = MockPlatform(None, config)
        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)

        args = [sys.executable, "-c",
                "import sys; sys.stdout.write('STDOUT'); sys.stderr.write('STDERR')"]

        with NamedTemporaryFile(delete=False, prefix="kruntest") as fh:
            filename = fh.name
            out, err, rv = vm_def._run_exec_popen(args, fh)

        assert err == ""  # not here due to redirection
        assert out == "STDOUT"  # behaviour should be unchanged
        assert rv == 0

        # stderr should be in this file
        with open(filename) as fh:
            assert fh.read() == "STDERR"

        fh.close()
        os.unlink(filename)

    def test_pypy_instrumentation0001(self):
        pypylog_file = StringIO("\n".join([
            "[41720a93ef67] {gc-minor",
            "[41720a941224] {gc-minor-walkroots",
            "[41720a942814] gc-minor-walkroots}",
            "[41720a9455be] gc-minor}",
            "@@@ END_IN_PROC_ITER: 0",
            "@@@ JIT_TIME: 0.001",
        ]))

        expect = {'raw_vm_events': [
            ['root', None, None, [
                ['gc-minor', 71958059544423, 71958059570622, [
                    ['gc-minor-walkroots', 71958059553316, 71958059558932, []]]]]]
            ],
            "jit_times": [0.001]}

        vmd = PyPyVMDef("/pretend/pypy")
        assert vmd.parse_instr_stderr_file(pypylog_file) == expect

    def test_pypy_instrumentation0002(self):
        pypylog_file = StringIO("\n".join([
            "[41720a93ef67] {gc-minor",
            "[41720a941224] {gc-minor-walkroots",
            "[41720a942814] gc-minor-walkroots}",
            "[41720a9455be] gc-minor}",
            "@@@ END_IN_PROC_ITER: 0",
            "@@@ JIT_TIME: 0.001",
            "[41720a93ef67] {gc-minor",
            "[41720a941224] {gc-minor-walkroots",
            "[41720a942814] gc-minor-walkroots}",
            "[41720a9455be] gc-minor}",
            "@@@ END_IN_PROC_ITER: 1",
            "@@@ JIT_TIME: 0.002",
        ]))

        expect_one_iter = ['root', None, None, [
            ['gc-minor', 71958059544423, 71958059570622, [
                ['gc-minor-walkroots', 71958059553316, 71958059558932, []]]]]
        ]
        expect = {'raw_vm_events': [
            expect_one_iter, expect_one_iter
            ],
            "jit_times": [0.001, 0.002]}

        vmd = PyPyVMDef("/pretend/pypy")
        assert vmd.parse_instr_stderr_file(pypylog_file) == expect

    def test_pypy_instrumentation0003(self):
        pypylog_file = StringIO("\n".join([
            "[41720a93ef67] {gc-minor",
            "[41720a900000] gc-minor}",  # stop time invalid
            "@@@ END_IN_PROC_ITER: 0",
            "@@@ JIT_TIME: 0.001",
        ]))

        vmd = PyPyVMDef("/pretend/pypy")
        with pytest.raises(AssertionError):
            vmd.parse_instr_stderr_file(pypylog_file)

    def test_pypy_instrumentation0004(self):
        pypylog_file = StringIO("\n".join([
            "[000000000001] {gc-minor",
            "[000000000002] {gc-step",
            "[000000000003] gc-minor}",  # bad nesting
            "[000000000004] gc-step}",
            "@@@ END_IN_PROC_ITER: 0",
            "@@@ JIT_TIME: 0.001",
        ]))

        vmd = PyPyVMDef("/pretend/pypy")
        with pytest.raises(AssertionError):
            vmd.parse_instr_stderr_file(pypylog_file)

    def test_pypy_instrumentation0005(self):
        pypylog_file = StringIO("\n".join([
            "[000000000001] {gc-minor",  # unfinished event
            "@@@ END_IN_PROC_ITER: 0",
            "@@@ JIT_TIME: 0.001",
        ]))

        vmd = PyPyVMDef("/pretend/pypy")
        with pytest.raises(AssertionError):
            vmd.parse_instr_stderr_file(pypylog_file)

    def test_jdk_instrumentation0001(self):
        """Check the json passes through correctly"""

        stderr_file = StringIO("\n".join([
            '@@@ JDK_EVENTS: [0, "dummy"]',
            '@@@ JDK_EVENTS: [1, "dummy"]',
            '@@@ JDK_EVENTS: [2, "dummy"]',
        ]))

        vmd = JavaVMDef("/pretend/java")
        got = vmd.parse_instr_stderr_file(stderr_file)

        elems = got["raw_vm_events"]
        assert len(elems) == 3
        for i in xrange(3):
            assert elems[i][0] == i

    def test_jdk_instrumentation0002(self):
        """Check the parser will bail if json entries out of sequence"""

        stderr_file = StringIO("\n".join([
            '@@@ JDK_EVENTS: [0, "dummy"]',
            '@@@ JDK_EVENTS: [3, "dummy"]',  # uh-oh!
            '@@@ JDK_EVENTS: [2, "dummy"]',
        ]))

        vmd = JavaVMDef("/pretend/java")
        with pytest.raises(AssertionError):
            vmd.parse_instr_stderr_file(stderr_file)
