from krun.tests import BaseKrunTest

class TestGenericPlatform(BaseKrunTest):
    """Platform tests that can be run on any platform"""

    def test_temperature_thresholds(self, mock_platform):
        temps = {"x": 30.0, "y": 12.34, "z": 666.0}
        mock_platform.starting_temperatures = temps

        for k, v in temps.iteritems():
            assert mock_platform.temperature_thresholds[k] == temps[k] + 5


