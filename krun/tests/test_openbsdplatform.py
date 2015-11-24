import pytest
import krun.platform
import sys
from krun.tests import BaseKrunTest, subst_env_arg
from krun.util import run_shell_cmd

def make_dummy_get_sysctl_temperature_output_fn(sysctl_output):
    def _get_sysctl_temperature_output(self):
        return sysctl_output
    return _get_sysctl_temperature_output

def make_dummy_get_apm_output_fn(output):
    def _get_apm_output(self):
        return output
    return _get_apm_output

@pytest.mark.skipif(not sys.platform.startswith("openbsd"), reason="not OpenBSD")
class TestOpenBSDPlatform(BaseKrunTest):
    """Check stuff specific to OpenBSD in krun.platform"""

    def test_read_temperatures0001(self, platform):
        temps = platform.take_temperature_readings()
        assert type(temps) is dict
        assert len(temps) > 0  # likely every system has at least one sensor
        assert all([x.startswith("hw.sensors.") for x in temps.iterkeys()])
        # check temperature readings are within reasonable parameters
        assert all([10 <= v <= 100 for v in temps.itervalues()])


    def test_read_broken_temperatures0001(self, monkeypatch, platform, caplog):
        # Unit is missing (expect degC suffix)
        broken_sysctl_output = "hw.sensors.some_temp0=10"

        monkey_func = make_dummy_get_sysctl_temperature_output_fn(broken_sysctl_output)
        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_get_sysctl_temperature_output", monkey_func)

        with pytest.raises(SystemExit):
            platform.take_temperature_readings()

        assert "odd non-degC value" in caplog.text()

    def test_read_broken_temperatures0002(self, monkeypatch, platform, caplog):
        # value (prior to degC) should be float()able
        broken_sysctl_output = "hw.sensors.some_temp0=inferno degC"

        monkey_func = make_dummy_get_sysctl_temperature_output_fn(broken_sysctl_output)
        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_get_sysctl_temperature_output", monkey_func)

        with pytest.raises(SystemExit):
            platform.take_temperature_readings()

        assert "non-numeric value" in caplog.text()

    def test_read_broken_temperatures0003(self, monkeypatch, platform, caplog):
        # Weird unit (not degC)
        broken_sysctl_output = "hw.sensors.some_temp0=66 kravits"

        monkey_func = make_dummy_get_sysctl_temperature_output_fn(broken_sysctl_output)
        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_get_sysctl_temperature_output", monkey_func)

        with pytest.raises(SystemExit):
            platform.take_temperature_readings()

        assert "odd non-degC value" in caplog.text()

    def test_apm_state0001(self, platform, caplog):
        run_shell_cmd("apm -C")  # cool mode; forces krun to change this.

        platform._check_apm_state()
        assert "performance mode is not manual" in caplog.text()
        # Hard to check hw.setperf, as it may well be temproarily 100
        assert "adjusting performance mode" in caplog.text()

        out, err, rc = run_shell_cmd("test `sysctl hw.setperf` == 'hw.setperf=100'")
        assert out == err == ""
        assert rc == 0

        # cool mode.
        # Sadly there is no way to query the current mode (e.g. -C or -H),
        # othwerwise we could restore the APM state to how the user had it
        # before.
        run_shell_cmd("apm -C")

    def test_apm_state0002(self, platform, caplog, monkeypatch):
        monkey_func = make_dummy_get_apm_output_fn("flibbles")
        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_get_apm_output", monkey_func)

        with pytest.raises(SystemExit):
            platform._check_apm_state()
        assert "Expected 3 lines of output from apm(8)" in caplog.text()

    def test_save_power0001(self, platform):
        run_shell_cmd("apm -H")
        platform.save_power()
        out, _, _ = run_shell_cmd("apm")
        lines = out.split("\n")
        line3 = lines[2].strip()
        assert line3.startswith("Performance adjustment mode: auto")
        # Would have been "manual" if we were still in "high-performance" mode.

    def test_bench_cmdline_adjust0001(self, platform):
        expect = ['doas', '-u', 'krun', 'nice', '-20', 'env',
                  'LD_LIBRARY_PATH=', 'MALLOC_OPTIONS=sdfghjpru']

        args = subst_env_arg(platform.bench_cmdline_adjust([], {}), "LD_LIBRARY_PATH")
        assert args == expect

    def test_bench_cmdline_adjust0002(self, platform):
        expect = ['doas', '-u', 'krun', 'nice', '-20', 'env',
                  'MYENV=some_value',
                  'LD_LIBRARY_PATH=', 'MALLOC_OPTIONS=sdfghjpru', 'myarg']

        args = subst_env_arg(platform.bench_cmdline_adjust(
            ["myarg"], {"MYENV": "some_value"}), "LD_LIBRARY_PATH")
        assert args == expect
