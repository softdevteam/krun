import subprocess32
import os
import sys
import pytest

# Some core cycle tests collect two readings as fast as possible, so the delta
# should be pretty small (but it ultimately depends upon the CPU).
NOT_MANY_CYCLES = 500000

DIR = os.path.abspath(os.path.dirname(__file__))
TEST_PROG_PATH = os.path.join(DIR, "test_prog")

sys.path.append(os.path.join(DIR, "..", ".."))
from krun.platform import detect_platform
PLATFORM = detect_platform(None, None)

MSR_SUPPORT = PLATFORM.num_per_core_measurements > 0

def invoke_c_prog(mode):
    assert os.path.exists(TEST_PROG_PATH)

    p = subprocess32.Popen(TEST_PROG_PATH + " " + mode,
        stderr=subprocess32.PIPE, stdout=subprocess32.PIPE, shell=True)
    out, err = p.communicate()
    return p.returncode, out.strip(), err.strip()


def parse_keyvals(out, doubles=False):
    dct = {}
    for line in out.splitlines():
        key, val = line.split("=")
        if doubles:
            dct[key.strip()] = float(val)
        else:
            dct[key.strip()] = int(val)
    return dct


class TestLibKrunTime(object):
    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_cycles_u64_0001(self):
        rv, out, _ = invoke_c_prog("cycles_u64")
        assert rv == 0
        dct = parse_keyvals(out)

        assert 0 <= dct["cycles_u64_delta"] <= NOT_MANY_CYCLES

    @pytest.mark.skipif(MSR_SUPPORT, reason="Without MSRs only")
    def test_cycles_u64_0002(self):
        rv, _, err = invoke_c_prog("cycles_u64")
        assert rv != 0
        assert "libkruntime was built without MSR support" in err

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_cycles_double(self):
        rv, out, _ = invoke_c_prog("cycles_double")
        assert rv == 0
        dct = parse_keyvals(out, True)
        assert 0 <= dct["cycles_double_delta"] <= NOT_MANY_CYCLES

    def test_cycles_double_prec_ok(self):
        rv, out, _ = invoke_c_prog("cycles_double_prec_ok")
        assert rv == 0
        assert out == "OK"

    def test_cycles_double_prec_bad(self):
        rv, _, err = invoke_c_prog("cycles_double_prec_bad")
        assert rv == 1
        assert "Loss of precision detected!" in err

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_cycles_u64_double_ratio(self):
        rv, out, _ = invoke_c_prog("cycles_u64_double_ratio")
        assert rv == 0
        dct = parse_keyvals(out, True)
        # within 2x of each other
        assert 0.5 <= dct["cycles_u64_double_ratio"] <= 2

    def test_clock_gettime_monotonic(self):
        rv, out, _ = invoke_c_prog("clock_gettime_monotonic")
        assert rv == 0
        dct = parse_keyvals(out, True)
        assert dct["monotonic_start"] <= dct["monotonic_stop"]

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_aperf_mperf(self):
        rv, out, _ = invoke_c_prog("aperf_mperf")
        assert rv == 0
        dct = parse_keyvals(out, doubles=False)

        assert dct["aperf"] > 0
        assert dct["mperf"] > 0

        # aperf is ticking for a subset of the time mperf is
        assert dct["aperf"] <= dct["mperf"]

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_aperf0001(self):
        """Check krun_get_aperf when libkruntime has MSR support"""

        rv, out, _ = invoke_c_prog("aperf")
        assert rv == 0
        dct = parse_keyvals(out)
        assert dct["aperf_start"] < dct["aperf_stop"]

    @pytest.mark.skipif(MSR_SUPPORT, reason="Without MSRs only")
    def test_aperf0002(self):
        """Check krun_get_aperf when libkruntime does not have MSR support"""

        rv, _, err = invoke_c_prog("aperf")
        assert rv != 0
        assert "libkruntime was built without MSR support" in err

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_mperf0001(self):
        """Check krun_get_mperf when libkruntime does not have MSR support"""

        rv, out, _ = invoke_c_prog("mperf")
        assert rv == 0
        dct = parse_keyvals(out)
        assert dct["mperf_start"] < dct["mperf_stop"]

    @pytest.mark.skipif(MSR_SUPPORT, reason="Without MSRs only")
    def test_mperf0002(self):
        """Check krun_get_aperf when libkruntime does not have MSR support"""

        rv, _, err = invoke_c_prog("mperf")
        assert rv != 0
        assert "libkruntime was built without MSR support" in err

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_core_bounds_check(self):
        rv, _, err = invoke_c_prog("core_bounds_check")
        assert rv != 0
        assert "core out of range" in err

    @pytest.mark.skipif(not MSR_SUPPORT, reason="No MSRs")
    def test_mdata_index_bounds_check(self):
        rv, _, err = invoke_c_prog("mdata_index_bounds_check")
        assert rv != 0
        assert "mdata index out of range" in err

    def test_read_everything_all_cores(self):
        rv, out, err = invoke_c_prog("read_everything_all_cores")
        assert rv == 0
        dct = parse_keyvals(out, doubles=True)

        # Two wallclock measurements
        expect = 2

        if MSR_SUPPORT:
            # Two more for measurements for each core
            expect += PLATFORM.num_cpus * 2
            # Two more for measurements for each aperf and mperf on each core
            expect += 2 * PLATFORM.num_cpus * 2

        assert len(dct) == expect
