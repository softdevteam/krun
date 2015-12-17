import pytest
from krun.vm_defs import BaseVMDef
from distutils.spawn import find_executable

class TestVMDef(object):
    """Test stuff in VM definitions"""

    def test_make_wrapper_script0001(self):
        args = ["arg1", "arg2", "arg3"]
        heap_lim_k = 1024 * 1024 * 1024  # 1GB
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

