import pytest
import krun.platform
from krun.tests import BaseKrunTest, subst_env_arg
import sys
from StringIO import StringIO


def mk_dummy_kernel_config_fn(options_dct):
    @staticmethod
    def wrap():
        fh = StringIO()
        for k, v in options_dct.iteritems():
            fh.write("%s=%s\n" % (k, v))
        fh.seek(0)
        return fh
    return wrap


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="not linux")
class TestLinuxPlatform(BaseKrunTest):
    """Check stuff specific to the Linux in krun.platform"""

    def test_tickless0001(self, monkeypatch, platform):
        """A kernel config indicating full tickless should work"""

        opts = {
            "CONFIG_NO_HZ_PERIODIC": "n",
            "CONFIG_NO_HZ_IDLE": "n",
            "CONFIG_NO_HZ_FULL": "y",
            "CONFIG_NO_HZ_FULL_ALL": "y",
        }

        mock_open_kernel_config_file = mk_dummy_kernel_config_fn(opts)
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_open_kernel_config_file",
                            mock_open_kernel_config_file)

        krun.platform.LinuxPlatform._check_tickless_kernel(platform)

    def test_tickless0002(self, monkeypatch, platform):
        """A kernel config indicating *not* full tickless should exit"""

        opts = {
            "CONFIG_NO_HZ_PERIODIC": "n",
            "CONFIG_NO_HZ_IDLE": "y",
            "CONFIG_NO_HZ_FULL": "n",
            "CONFIG_NO_HZ_FULL_ALL": "n",
        }

        mock_open_kernel_config_file = mk_dummy_kernel_config_fn(opts)
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_open_kernel_config_file",
                            mock_open_kernel_config_file)

        with pytest.raises(SystemExit):
            krun.platform.LinuxPlatform._check_tickless_kernel(platform)

    def test_tickless0003(self, monkeypatch, platform):
        """A kernel config making no sense, should exit"""

        # This contrived input appears to have two different tick modes enabled
        opts = {
            "CONFIG_NO_HZ_PERIODIC": "n",
            "CONFIG_NO_HZ_IDLE": "y",
            "CONFIG_NO_HZ_FULL": "y",
            "CONFIG_NO_HZ_FULL_ALL": "y",
        }

        mock_open_kernel_config_file = mk_dummy_kernel_config_fn(opts)
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_open_kernel_config_file",
                            mock_open_kernel_config_file)

        with pytest.raises(SystemExit):
            krun.platform.LinuxPlatform._check_tickless_kernel(platform)

    def test_tickless0004(self, monkeypatch, platform):
        """A kernel config indicating no tick mode should exit"""

        opts = {
            "CONFIG_NO_HZ_PERIODIC": "n",
            "CONFIG_NO_HZ_IDLE": "n",
            "CONFIG_NO_HZ_FULL": "n",
            "CONFIG_NO_HZ_FULL_ALL": "n",
        }

        mock_open_kernel_config_file = mk_dummy_kernel_config_fn(opts)
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_open_kernel_config_file",
                            mock_open_kernel_config_file)

        with pytest.raises(SystemExit):
            krun.platform.LinuxPlatform._check_tickless_kernel(platform)

    def test_tickless0005(self, monkeypatch, platform, caplog):
        """Adaptive-tick mode CPUs should not be overridden"""

        def dummy_get_kernel_cmdline(_self):
            # nohz_full overrides adaptive-tick CPU list
            return "BOOT_IMAGE=/boot/blah nohz_full=1"

        opts = {
            "CONFIG_NO_HZ_PERIODIC": "n",
            "CONFIG_NO_HZ_IDLE": "n",
            "CONFIG_NO_HZ_FULL": "y",
            "CONFIG_NO_HZ_FULL_ALL": "y",
        }

        mock_open_kernel_config_file = mk_dummy_kernel_config_fn(opts)
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_open_kernel_config_file",
                            mock_open_kernel_config_file)
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_get_kernel_cmdline",
                            dummy_get_kernel_cmdline)

        with pytest.raises(SystemExit):
            krun.platform.LinuxPlatform._check_tickless_kernel(platform)

        assert "Adaptive-ticks CPUs overridden on kernel command line" \
            in caplog.text()

    def test_bench_cmdline_adjust0001(self, platform):
        expect = ['nice', '-20', 'env', 'LD_LIBRARY_PATH=']

        args = subst_env_arg(platform.bench_cmdline_adjust([], {}), "LD_LIBRARY_PATH")
        assert args == expect

    def test_bench_cmdline_adjust0002(self, platform):
        expect = ['nice', '-20', 'env', 'MYENV=some_value',
                  'LD_LIBRARY_PATH=', 'myarg']

        args = subst_env_arg(platform.bench_cmdline_adjust(
            ["myarg"], {"MYENV": "some_value"}), "LD_LIBRARY_PATH")

        assert args == expect
