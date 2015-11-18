import pytest
import krun.platform
import sys
from krun.tests import BaseKrunTest

def make_dummy_get_sysctl_temperature_output_fn(sysctl_output):
    def _get_sysctl_temperature_output(self):
        return sysctl_output
    return _get_sysctl_temperature_output


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
