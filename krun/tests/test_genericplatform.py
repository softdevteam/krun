from krun.tests import BaseKrunTest
from krun.util import FatalKrunError
import pytest

class TestGenericPlatform(BaseKrunTest):
    """Platform tests that can be run on any platform"""

    def test_temperature_thresholds(self, mock_platform):
        temps = {"x": 30.0, "y": 12.34, "z": 666.0}
        mock_platform.temp_sensors = ["x", "y", "z"]
        mock_platform.starting_temperatures = temps

        for k, v in temps.iteritems():
            assert mock_platform.temperature_thresholds[k] == temps[k] + 1

    def test_inconsistent_sensors0001(self, platform, caplog):
        # The platform has already detected the available sensors. Now we
        # confuse it, by moving a sensor. This shouldn't happen of course, but
        # tests are good nevertheless.

        if not platform.temp_sensors:
            pytest.skip("no temperature sensors")

        platform.temp_sensors[0] += "_moved"

        with pytest.raises(FatalKrunError):
            platform.take_temperature_readings()

        expect = "Failed to read sensor"
        assert expect in caplog.text()


    def test_inconsistent_sensors0002(self, platform, caplog):
        platform.temp_sensors = ["different", "sensors"]

        with pytest.raises(FatalKrunError):
            platform.starting_temperatures = {"a": 1000, "b": 2000}

        expect = "Inconsistent sensors. ['a', 'b'] vs ['different', 'sensors']"
        assert expect in caplog.text()

    def test_inconsistent_sensors0003(self, platform, caplog):
        platform.temp_sensors = ["a"]

        with pytest.raises(FatalKrunError):
            platform.starting_temperatures = {"a": 1000, "b": 2000}

        expect = "Inconsistent sensors. ['a', 'b'] vs ['a']"
        assert expect in caplog.text()
