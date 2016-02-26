import pytest
from krun.vm_defs import BaseVMDef, PythonVMDef, PyPyVMDef
from distutils.spawn import find_executable
from krun.env import EnvChange
from krun.tests.mocks import MockPlatform
from krun import EntryPoint
from krun import util

class TestVMDef(object):
    """Test stuff in VM definitions"""

    def test_make_wrapper_script0001(self):
        args = ["arg1", "arg2", "arg3"]
        heap_lim_k = 1024 * 1024 * 1024  # 1GiB
        stack_lim_k = 8192
        dash = find_executable("dash")
        assert dash is not None

        expect = [
            '#!%s' % dash,
            'ulimit -d %s || exit $?' % heap_lim_k,
            'ulimit -s %s || exit $?' % stack_lim_k,
            'arg1 arg2 arg3',
            'exit $?'
        ]

        got = BaseVMDef.make_wrapper_script(args, heap_lim_k, stack_lim_k)
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

        ec1= vm.common_env_changes[0]
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

        platform = MockPlatform(None)
        ep = EntryPoint("test")
        vm_def = PythonVMDef('/dummy/bin//python')
        vm_def.set_platform(platform)

        sync_called = [False]
        def fake_sync_disks():
            sync_called[0] = True
        monkeypatch.setattr(platform, "sync_disks", fake_sync_disks)

        def fake_run_exec_popen(args):
            return "[1]", "", 0  # stdout, stderr, exit_code
        monkeypatch.setattr(vm_def, "_run_exec_popen", fake_run_exec_popen)

        vm_def.run_exec(ep, "test", 1, 1, 1, 1)
        assert sync_called == [True]

    def test_sync_disks0002(self, monkeypatch):
        """We throw away the results from sanity checks, so there's no need to
        sync disks (and wait)."""

        platform = MockPlatform(None)
        ep = EntryPoint("test")
        vm_def = PythonVMDef('/dummy/bin//python')

        sync_called = [False]
        def fake_sync_disks():
            sync_called[0] = True
        monkeypatch.setattr(platform, "sync_disks", fake_sync_disks)

        def fake_run_exec_popen(args):
            return "[1]", "", 0  # stdout, stderr, exit_code
        monkeypatch.setattr(vm_def, "_run_exec_popen", fake_run_exec_popen)

        util.spawn_sanity_check(platform, ep, vm_def, "test")
        assert sync_called == [False]
