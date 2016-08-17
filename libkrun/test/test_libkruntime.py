from subprocess import Popen, PIPE
import os

# Some TSR tests collect two TSR readings as fast as possible, so the delta
# should be pretty small (but it ultimately depends upon the CPU).
NOT_MANY_CYCLES = 5000

DIR = os.path.abspath(os.path.dirname(__file__))
TEST_PROG_PATH = os.path.join(DIR, "test_prog")


def invoke_c_prog(mode):
    assert os.path.exists(TEST_PROG_PATH)

    p = Popen(TEST_PROG_PATH + " " + mode,
              stderr=PIPE, stdout=PIPE, shell=True)
    out, err = p.communicate()
    return p.returncode, out.strip(), err.strip()


def parse_keyvals(out, doubles=True):
    dct = {}
    for line in out.splitlines():
        key, val = line.split("=")
        if doubles:
            dct[key.strip()] = float(val)
        else:
            dct[key.strip()] = int(val)
    return dct


class TestLibKrunTime(object):
    def test_tsr_u64(self):
        rv, out, _ = invoke_c_prog("tsr_u64")
        assert rv == 0
        dct = parse_keyvals(out)
        assert 0 <= dct["tsr_u64_delta"] <= NOT_MANY_CYCLES

    def test_tsr_double(self):
        rv, out, _ = invoke_c_prog("tsr_double")
        assert rv == 0
        dct = parse_keyvals(out, True)
        assert 0 <= dct["tsr_double_delta"] <= NOT_MANY_CYCLES

    def test_tsr_double_prec_ok(self):
        rv, out, _ = invoke_c_prog("tsr_double_prec_ok")
        assert rv == 0
        assert out == "OK"

    def test_tsr_double_prec_bad(self):
        rv, _, err = invoke_c_prog("tsr_double_prec_bad")
        assert rv == 1
        assert "Loss of precision detected!" in err

    def test_tsr_u64_double_ratio(self):
        rv, out, _ = invoke_c_prog("tsr_u64_double_ratio")
        assert rv == 0
        dct = parse_keyvals(out, True)
        # The integer version should always be faster
        assert dct["tsr_u64_double_ratio"] <= 1

    def test_clock_gettime_monotonic(self):
        rv, out, _ = invoke_c_prog("clock_gettime_monotonic")
        assert rv == 0
        dct = parse_keyvals(out)
        # Depends on speed of CPU, but should be very close to 1
        assert 0.95 <= dct["monotonic_delta"] <= 1.05
