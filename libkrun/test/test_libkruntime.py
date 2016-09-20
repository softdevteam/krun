from subprocess import Popen, PIPE
import os
import glob
import sys
import pytest

# Some core cycle tests collect two readings as fast as possible, so the delta
# should be pretty small (but it ultimately depends upon the CPU).
NOT_MANY_CYCLES = 500000

DIR = os.path.abspath(os.path.dirname(__file__))
TEST_PROG_PATH = os.path.join(DIR, "test_prog")

sys.path.append(os.path.join(DIR, "..", ".."))
from krun.platform import detect_platform
platform = detect_platform(None, None)

CORECYCLES_SUPPORT = sys.platform.startswith("linux") and \
    not (os.environ.get("TRAVIS", None) == "true")

APERF_MPERF_SUPPORT = sys.platform.startswith("linux") and \
    not (os.environ.get("TRAVIS", None) == "true")

def invoke_c_prog(mode):
    assert os.path.exists(TEST_PROG_PATH)

    p = Popen(TEST_PROG_PATH + " " + mode,
              stderr=PIPE, stdout=PIPE, shell=True)
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
    def test_cycles_u64(self):
        rv, out, _ = invoke_c_prog("cycles_u64")
        assert rv == 0
        dct = parse_keyvals(out)

        if CORECYCLES_SUPPORT:
            assert 0 <= dct["cycles_u64_delta"] <= NOT_MANY_CYCLES
        else:
            assert dct["cycles_u64_start"] == 0
            assert dct["cycles_u64_stop"] == 0
            assert dct["cycles_u64_delta"] == 0

    def test_cycles_double(self):
        rv, out, _ = invoke_c_prog("cycles_double")
        assert rv == 0
        dct = parse_keyvals(out, True)
        if CORECYCLES_SUPPORT:
            assert 0 <= dct["cycles_double_delta"] <= NOT_MANY_CYCLES
        else:
            assert dct["cycles_double_start"] == 0.0
            assert dct["cycles_double_stop"] == 0.0
            assert dct["cycles_double_delta"] == 0.0

    def test_cycles_double_prec_ok(self):
        rv, out, _ = invoke_c_prog("cycles_double_prec_ok")
        assert rv == 0
        assert out == "OK"

    def test_cycles_double_prec_bad(self):
        rv, _, err = invoke_c_prog("cycles_double_prec_bad")
        assert rv == 1
        assert "Loss of precision detected!" in err

    @pytest.mark.skipif(not CORECYCLES_SUPPORT, reason="would divide by zero")
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
        # Depends on speed of CPU, but should be very close to 1
        assert 0.95 <= dct["monotonic_delta"] <= 1.05

    @pytest.mark.skipif(not CORECYCLES_SUPPORT, reason="would not make sense")
    def test_msr_time(self):
        rv, out, _ = invoke_c_prog("msr_time")
        assert rv == 0
        dct = parse_keyvals(out, True)

        # On Linux I expect reading core cycles (via the MSR device nodes) to
        # be slower than reading the monotonic clock via a system call. This
        # is why the readings are ordered as they are in the iterations runner.
        assert dct["monotonic_delta_msrs"] > dct["monotonic_delta_nothing"]

    def test_aperf_mperf(self):
        rv, out, _ = invoke_c_prog("aperf_mperf")
        assert rv == 0
        dct = parse_keyvals(out, doubles=False)
        if APERF_MPERF_SUPPORT:
            assert dct["aperf"] > 0
            assert dct["mperf"] > 0

            # aperf is ticking for a subset of the time mperf is
            assert dct["aperf"] <= dct["mperf"]
        else:
            assert dct["aperf"] == 0
            assert dct["mperf"] == 0

    def test_aperf(self):
        rv, out, _ = invoke_c_prog("aperf")
        assert rv == 0
        dct = parse_keyvals(out)
        if APERF_MPERF_SUPPORT:
            assert dct["aperf_start"] < dct["aperf_stop"]
        else:
            assert dct["aperf_start"] == 0
            assert dct["aperf_stop"] == 0

    def test_mperf(self):
        rv, out, _ = invoke_c_prog("mperf")
        assert rv == 0
        dct = parse_keyvals(out)
        if APERF_MPERF_SUPPORT:
            assert dct["mperf_start"] < dct["mperf_stop"]
        else:
            assert dct["mperf_start"] == 0
            assert dct["mperf_stop"] == 0
