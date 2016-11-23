import pytest
import krun.platform
import sys
from krun.tests import BaseKrunTest, subst_env_arg
from krun.util import run_shell_cmd, FatalKrunError
from krun.vm_defs import PythonVMDef


def make_dummy_get_apm_output_fn(output):
    def _get_apm_output(self):
        return output
    return _get_apm_output

@pytest.mark.skipif(not sys.platform.startswith("openbsd"), reason="not OpenBSD")
class TestOpenBSDPlatform(BaseKrunTest):
    """Check stuff specific to OpenBSD in krun.platform"""

    def test_take_temperature_readings0001(self, platform):
        """Test live readings off test machine"""

        temps = platform.take_temperature_readings()
        assert type(temps) is dict
        assert all([x.startswith("hw.sensors.") for x in temps.iterkeys()])
        # check temperature readings are within reasonable parameters
        assert all([type(v) == float for v in temps.itervalues()])
        assert all([10 <= v <= 120 for v in temps.itervalues()])

    def test_take_temperature_readings0002(self, platform, monkeypatch):
        """Test with fake readings"""

        platform.temp_sensors = [
            "hw.sensors.cpu0.temp0",
            "hw.sensors.acpitz0.temp0",
        ]

        def fake__raw_read_temperature_sensor(self, sensor):
            if sensor == "hw.sensors.cpu0.temp0":
                return "hw.sensors.cpu0.temp0=64.00 degC"
            elif sensor == "hw.sensors.acpitz0.temp0":
                return "hw.sensors.acpitz0.temp0=65.58 degC (zone temperature)"
            else:
                assert False

        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_raw_read_temperature_sensor",
                            fake__raw_read_temperature_sensor)

        # Results were already in degrees C
        expect = {
            "hw.sensors.cpu0.temp0": 64.00,
            "hw.sensors.acpitz0.temp0": 65.58,
        }
        got = platform.take_temperature_readings()

        assert expect == got

    def test_read_broken_temperatures0001(self, monkeypatch, platform, caplog):
        platform.temp_sensors = ["hw.sensors.some_temp0"]

        def dummy(self, sensor):
            # Unit is missing (expect degC suffix)
            return "hw.sensors.some_temp0=10"

        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_raw_read_temperature_sensor", dummy)

        with pytest.raises(FatalKrunError):
            platform.take_temperature_readings()

        assert "Odd non-degC value" in caplog.text()

    def test_read_broken_temperatures0002(self, monkeypatch, platform, caplog):
        platform.temp_sensors = ["hw.sensors.some_temp0"]

        def dummy(self, sensor):
            # value (prior to degC) should be float()able
            return "hw.sensors.some_temp0=inferno degC"

        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_raw_read_temperature_sensor", dummy)

        with pytest.raises(FatalKrunError):
            platform.take_temperature_readings()

        assert "Non-numeric value" in caplog.text()

    def test_read_broken_temperatures0003(self, monkeypatch, platform, caplog):
        platform.temp_sensors = ["hw.sensors.some_temp0"]

        def dummy(self, sensor):
            # Weird unit (not degC)
            return "hw.sensors.some_temp0=66 kravits"

        monkeypatch.setattr(krun.platform.OpenBSDPlatform,
                            "_raw_read_temperature_sensor", dummy)

        with pytest.raises(FatalKrunError):
            platform.take_temperature_readings()

        assert "Odd non-degC value" in caplog.text()

    def test_apm_state0001(self, platform, caplog):
        run_shell_cmd("apm -C")  # cool mode; forces krun to change this.

        platform._check_apm_state()

        if "hw.setperf is not available" in caplog.text():
            pytest.skip()

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

        with pytest.raises(FatalKrunError):
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
        expect = ['env', 'LD_LIBRARY_PATH=', 'MALLOC_OPTIONS=sfghjpru']

        args = subst_env_arg(platform.bench_cmdline_adjust([], {}), "LD_LIBRARY_PATH")
        assert args == expect

    def test_bench_cmdline_adjust0002(self, platform):
        expect = ['env', 'MYENV=some_value', 'LD_LIBRARY_PATH=',
                  'MALLOC_OPTIONS=sfghjpru', 'myarg']

        args = subst_env_arg(platform.bench_cmdline_adjust(
            ["myarg"], {"MYENV": "some_value"}), "LD_LIBRARY_PATH")
        assert args == expect

    def test_wrapper_args0001(self, platform):
        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)
        wrapper_filename = "/tmp/abcdefg.dash"
        got = vm_def._wrapper_args(wrapper_filename)
        expect = ['/usr/local/bin/sudo', '-u', 'root', '/usr/bin/nice', '-n', '-20',
                  '/usr/local/bin/sudo', '-u', 'krun', '/usr/local/bin/dash',
                  wrapper_filename]
        assert got == expect

    def test_wrapper_args0002(self, platform):
        # Pinning isn't supported on OpenBSD, so it should make no difference
        platform.config.ENABLE_PINNING = False

        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)
        wrapper_filename = "/tmp/abcdefg.dash"
        got = vm_def._wrapper_args(wrapper_filename)
        expect = ['/usr/local/bin/sudo', '-u', 'root', '/usr/bin/nice', '-n', '-20',
                  '/usr/local/bin/sudo', '-u', 'krun', '/usr/local/bin/dash',
                  wrapper_filename]
        assert got == expect
