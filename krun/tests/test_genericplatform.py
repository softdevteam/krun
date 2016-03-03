from krun.tests import BaseKrunTest, no_sleep
from krun.util import FatalKrunError
import pytest

class TestGenericPlatform(BaseKrunTest):
    """Platform tests that can be run on any platform"""

    def test_temperature_thresholds0001(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0, "y": 12.34, "z": 666.0}
        mock_platform.temp_sensors = ["x", "y", "z"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            # a little hotter than we started
            return {name: temp + 1 for name, temp in temps.iteritems()}
        monkeypatch.setattr(mock_platform,"take_temperature_readings",
                            mock_take_temperature_readings)

        mock_platform.wait_for_temperature_sensors()
        # should exit without crashing, no assert.

    def test_temperature_thresholds0002(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0}
        mock_platform.temp_sensors = ["x"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            return {"x": 999}  # system on fire
        monkeypatch.setattr(mock_platform,"take_temperature_readings",
                            mock_take_temperature_readings)

        with pytest.raises(FatalKrunError):
            mock_platform.wait_for_temperature_sensors()

        expect = ("Temperature timeout: Temperature reading 'x' not "
                  "within interval: (27 <= 999 <= 33)")
        assert expect in caplog.text()

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
