from krun.tests import BaseKrunTest

class TestGenericPlatform(BaseKrunTest):
    """Platform tests that can be run on any platform"""

    def test_temperature_thresholds(self, mock_platform):
        temps = {"x": 3000, "y": 1234, "z": 666}
        mock_platform.starting_temperatures = temps

        for k, v in temps.iteritems():
            # should be 10% higher
            assert mock_platform.temperature_thresholds[k] ==\
                int(temps[k] *  1.1)


