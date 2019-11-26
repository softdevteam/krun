from krun.tests import BaseKrunTest
from krun.util import FatalKrunError
from krun.platform import BasePlatform
from krun.tests.mocks import mock_manifest
import pytest
import re

class TestGenericPlatform(BaseKrunTest):
    """Platform tests that can be run on any platform"""

    def test_temperature_thresholds0001(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0, "y": 12.34, "z": 666.0}
        mock_platform.temp_sensors = ["x", "y", "z"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            # a little hotter than we started
            return {name: temp + 1 for name, temp in temps.iteritems()}
        monkeypatch.setattr(mock_platform, "take_temperature_readings",
                            mock_take_temperature_readings)

        mock_platform.wait_for_temperature_sensors(testing=True)
        # should exit without crashing, no assert.

    def test_temperature_thresholds0002(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0}
        mock_platform.temp_sensors = ["x"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            return {"x": 999}  # system on fire
        monkeypatch.setattr(mock_platform, "take_temperature_readings",
                            mock_take_temperature_readings)

        with pytest.raises(FatalKrunError):
            mock_platform.wait_for_temperature_sensors(testing=True)

        expect = ("Temperature timeout: Temperature reading 'x' not "
                  "within interval: (27 <= 999 <= 33)")
        assert expect in caplog.text()

    def test_temperature_thresholds0003(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0}
        mock_platform.temp_sensors = ["x"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            return {"x": -999}  # system in the arctic
        monkeypatch.setattr(mock_platform, "take_temperature_readings",
                            mock_take_temperature_readings)

        with pytest.raises(FatalKrunError):
            mock_platform.wait_for_temperature_sensors(testing=True)

        expect = ("Temperature timeout: Temperature reading 'x' not "
                  "within interval: (27 <= -999 <= 33)")
        assert expect in caplog.text()

    def test_temperature_thresholds0004(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0}
        mock_platform.temp_sensors = ["x"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            return {"x": 999}  # system on fire
        monkeypatch.setattr(mock_platform, "take_temperature_readings",
                            mock_take_temperature_readings)

        flag, _ = mock_platform.temp_sensors_within_interval()
        assert flag == BasePlatform.TEMP_TOO_HOT

    def test_temperature_thresholds0005(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0}
        mock_platform.temp_sensors = ["x"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            return {"x": -999}  # system in the arctic again
        monkeypatch.setattr(mock_platform, "take_temperature_readings",
                            mock_take_temperature_readings)

        flag, _ = mock_platform.temp_sensors_within_interval()
        assert flag == BasePlatform.TEMP_TOO_COLD

    def test_temperature_thresholds0006(self, mock_platform, monkeypatch, caplog):
        temps = {"x": 30.0}
        mock_platform.temp_sensors = ["x"]
        mock_platform.starting_temperatures = temps

        def mock_take_temperature_readings():
            return {"x": 31}  # almost spot on
        monkeypatch.setattr(mock_platform, "take_temperature_readings",
                            mock_take_temperature_readings)

        flag, _ = mock_platform.temp_sensors_within_interval()
        assert flag == BasePlatform.TEMP_OK

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

    def test_dmesg_filter0001(self, mock_platform, caplog, mock_manifest):
        last_dmesg = ["line1", "line2"]
        new_dmesg = ["line1", "line2", "line3"]

        # this should indicate change
        assert mock_platform._check_dmesg_for_changes(
            [], last_dmesg, new_dmesg, mock_manifest)

        # and the log will indicate this also
        assert "New dmesg lines" in caplog.text()
        assert "\nline3" in caplog.text()

    def test_dmesg_filter0002(self, mock_platform, caplog, mock_manifest):
        last_dmesg = ["line1", "line2"]
        new_dmesg = ["line1", "line2", "sliced_bread"]

        # this should indicate no change because we allowed the change
        patterns = [re.compile("red.*herring"), re.compile("sl[ixd]c.*bread$")]
        assert not mock_platform._check_dmesg_for_changes(
            patterns, last_dmesg, new_dmesg, mock_manifest)

    def test_dmesg_filter0003(self, mock_platform, caplog, mock_manifest):
        # simulate 2 lines falling off the top of the dmesg buffer
        last_dmesg = ["line1", "line2", "line3", "line4"]
        new_dmesg = ["line3", "line4"]

        # despite lines dropping off, this should still indicate no change
        assert not mock_platform._check_dmesg_for_changes(
            [], last_dmesg, new_dmesg, mock_manifest)

    def test_dmesg_filter0004(self, mock_platform, caplog, mock_manifest):
        # simulate 2 lines falling off the top of the dmesg buffer, *and* a
        # new line coming on the bottom of the buffer.
        last_dmesg = ["line1", "line2", "line3", "line4"]
        new_dmesg = ["line3", "line4", "line5"]

        # line5 is a problem
        assert mock_platform._check_dmesg_for_changes(
            [], last_dmesg, new_dmesg, mock_manifest)
        assert "\nline5\n" in caplog.text()
        for num in xrange(1, 5):
            assert not ("\nline%s\n" % num) in caplog.text()

    def test_dmesg_filter0005(self, mock_platform, caplog, mock_manifest):
        # simulate 2 lines falling off the top of the dmesg buffer, *and* a
        # new line coming on the bottom of the buffer, but the filter accepts
        # the new line.
        last_dmesg = ["line1", "line2", "line3", "line4"]
        new_dmesg = ["line3", "line4", "line5"]

        patterns = [re.compile(".*5$")]
        assert not mock_platform._check_dmesg_for_changes(
            patterns, last_dmesg, new_dmesg, mock_manifest)

    def test_dmesg_filter0006(self, mock_platform, caplog, mock_manifest):
        # Simulate partial line falling off the dmesg buffer due to a new line.
        # The change incurred by the partial line should not trigger our "dmesg
        # changed" flagging code.
        last_dmesg = ["line1", "line2", "line3"]
        new_dmesg = ["e1", "line2", "line3", "xx"]  # 3 chars 'xx\n'

        patterns = [re.compile("^xx$")]
        assert not mock_platform._check_dmesg_for_changes(
            patterns, last_dmesg, new_dmesg, mock_manifest)

    def test_dmesg_filter0007(self, mock_platform, caplog, mock_manifest):
        # Simulate partial dmesg buffer completely replaced!
        # This should be an error as we have potentially missed other
        # important messages that flew off the top of the buffer too!
        last_dmesg = ["x", "x", "x"]
        new_dmesg = ["y", "y", "y"]

        assert mock_platform._check_dmesg_for_changes(
            [], last_dmesg, new_dmesg, mock_manifest)
