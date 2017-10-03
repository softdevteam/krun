# Copyright (c) 2017 King's College London
# created by the Software Development Team <http://soft-dev.org/>
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or
# data (collectively the "Software"), free of charge and under any and all
# copyright rights in the Software, and any and all patent rights owned or
# freely licensable by each licensor hereunder covering either (i) the
# unmodified Software as contributed to or provided by such licensor, or (ii)
# the Larger Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
# one is included with the Software (each a "Larger Work" to which the Software
# is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright
# notice and either this complete permission notice or at a minimum a reference
# to the UPL must be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import pytest
import krun.platform
from krun.platform import LinuxPlatform
from krun.tests import BaseKrunTest, subst_env_arg
from krun.util import FatalKrunError, run_shell_cmd
from krun.vm_defs import  PythonVMDef
from krun.tests.mocks import mock_manifest
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

        with pytest.raises(FatalKrunError):
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

        with pytest.raises(FatalKrunError):
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

        with pytest.raises(FatalKrunError):
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

        with pytest.raises(FatalKrunError):
            krun.platform.LinuxPlatform._check_tickless_kernel(platform)

        assert "Adaptive-ticks CPUs overridden on kernel command line" \
            in caplog.text()

    def test_bench_cmdline_adjust0001(self, platform):
        expect = ['env', 'LD_LIBRARY_PATH=']

        args = subst_env_arg(platform.bench_cmdline_adjust([], {}), "LD_LIBRARY_PATH")
        assert args == expect

    def test_bench_cmdline_adjust0002(self, platform):
        expect = ['env', 'MYENV=some_value', 'LD_LIBRARY_PATH=', 'myarg']

        args = subst_env_arg(platform.bench_cmdline_adjust(
            ["myarg"], {"MYENV": "some_value"}), "LD_LIBRARY_PATH")

        assert args == expect

    def test_bench_cmdline_adjust0003(self, platform):
        expect = ['env', 'LD_LIBRARY_PATH=']

        args = subst_env_arg(platform.bench_cmdline_adjust([], {}), "LD_LIBRARY_PATH")
        assert args == expect

    def test_pin_process_args0001(self, platform):
        platform.num_cpus = 2
        expect = ['/usr/bin/sudo', '-u', 'root', '/usr/bin/cset', 'shield', '-e', '--']

        got = platform.pin_process_args()
        assert got == expect

    def test_configure_cset_shield_args0001(self, platform):
        platform.num_cpus = 4
        platform.config.ENABLE_PINNING = True
        got = platform._configure_cset_shield_args()
        expect = [['/usr/bin/sudo', '-u', 'root', '/usr/bin/cset',
                   'shield', '-c', '1-3'],
                  ['/usr/bin/cset', 'shield', '-k', 'on']]
        assert got == expect

    def test_configure_cset_shield_args0002(self, platform):
        platform.config.ENABLE_PINNING = True
        platform.num_cpus = 128
        got = platform._configure_cset_shield_args()
        expect = [['/usr/bin/sudo', '-u', 'root', '/usr/bin/cset',
                   'shield', '-c', '1-127'],
                  ['/usr/bin/cset', 'shield', '-k', 'on']]
        assert got == expect

    def test_wrapper_args0001(self, platform):
        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)
        wrapper_filename = "abcdefg.dash"
        got = vm_def._wrapper_args(wrapper_filename)
        expect = ['/usr/bin/sudo', '-u', 'root', '/usr/bin/nice', '-n', '-20',
                  '/usr/bin/sudo', '-u', 'krun', '/bin/dash', wrapper_filename]
        assert got == expect

    def test_wrapper_args0002(self, platform):
        platform.config.ENABLE_PINNING = False

        vm_def = PythonVMDef('/dummy/bin/python')
        vm_def.set_platform(platform)
        wrapper_filename = "abcdefg.dash"
        got = vm_def._wrapper_args(wrapper_filename)
        expect = ['/usr/bin/sudo', '-u', 'root', '/usr/bin/nice', '-n', '-20',
                  '/usr/bin/sudo', '-u', 'krun', '/bin/dash', wrapper_filename]
        assert got == expect

    def test_take_temperature_readings0001(self, platform):
        """Test live readings off test machine"""

        temps = platform.take_temperature_readings()
        assert type(temps) is dict

        for sid in temps.iterkeys():
            elems = sid.split(":")
            assert len(elems) == 3
            assert elems[2].endswith("_input")

        # check temperature readings are within reasonable parameters
        assert all([type(v) == float for v in temps.itervalues()])
        assert all([10 <= v <= 100 for v in temps.itervalues()])

    def test_take_temperature_readings0002(self, platform, monkeypatch):
        platform.temp_sensors = [
            "x:temp1_input",
            "y:temp1_input",
            "y:temp2_input",
        ]

        def fake_read_zone(self, zone):
            if zone == "x:temp1_input":
                return 66123
            elif zone == "y:temp1_input":
                return 0
            else:
                return 100000

        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_read_temperature_sensor", fake_read_zone)

        expect = {
            "x:temp1_input": 66.123,
            "y:temp1_input": 0.0,
            "y:temp2_input": 100.0
        }
        got = platform.take_temperature_readings()

        assert expect == got

    def test_find_temperature_sensors0001(self, monkeypatch):
        """Test your typical Linux machine"""

        @staticmethod
        def fake_collect_temperature_sensor_globs():
            return {'/sys/class/hwmon/hwmon0':
                    ('coretemp', [
                        '/sys/class/hwmon/hwmon0/temp2_input',
                        '/sys/class/hwmon/hwmon0/temp5_input',
                        '/sys/class/hwmon/hwmon0/temp3_input',
                        '/sys/class/hwmon/hwmon0/temp1_input',
                        '/sys/class/hwmon/hwmon0/temp4_input'])}
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_collect_temperature_sensor_globs",
                            fake_collect_temperature_sensor_globs)
        platform = krun.platform.detect_platform(None, None)
        assert platform.temp_sensor_map == {
            'coretemp:5:temp5_input': '/sys/class/hwmon/hwmon0/temp5_input',
            'coretemp:5:temp4_input': '/sys/class/hwmon/hwmon0/temp4_input',
            'coretemp:5:temp3_input': '/sys/class/hwmon/hwmon0/temp3_input',
            'coretemp:5:temp2_input': '/sys/class/hwmon/hwmon0/temp2_input',
            'coretemp:5:temp1_input': '/sys/class/hwmon/hwmon0/temp1_input'
        }

    def test_find_temperature_sensors0002(self, monkeypatch, caplog):
        """Test one un-named chip"""

        @staticmethod
        def fake_collect_temperature_sensor_globs():
            return {'/sys/class/hwmon/hwmon0':
                    ('coretemp', [
                        '/sys/class/hwmon/hwmon0/temp2_input',
                        '/sys/class/hwmon/hwmon0/temp5_input',
                        '/sys/class/hwmon/hwmon0/temp3_input',
                        '/sys/class/hwmon/hwmon0/temp1_input',
                        '/sys/class/hwmon/hwmon0/temp4_input']),
                    '/sys/class/hwmon/hwmon1':
                    (None, ['/sys/class/hwmon/hwmon1/temp1_input'])}
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_collect_temperature_sensor_globs",
                            fake_collect_temperature_sensor_globs)
        platform = krun.platform.detect_platform(None, None)
        assert platform.temp_sensor_map == {
            'coretemp:5:temp4_input': '/sys/class/hwmon/hwmon0/temp4_input',
            'coretemp:5:temp3_input': '/sys/class/hwmon/hwmon0/temp3_input',
            'coretemp:5:temp2_input': '/sys/class/hwmon/hwmon0/temp2_input',
            'coretemp:5:temp1_input': '/sys/class/hwmon/hwmon0/temp1_input',
            '__krun_unknown_chip_name:1:temp1_input':
                '/sys/class/hwmon/hwmon1/temp1_input',
            'coretemp:5:temp5_input': '/sys/class/hwmon/hwmon0/temp5_input'}
        assert "Un-named temperature sensor chip found" in caplog.text()

    def test_find_temperature_sensors0003(self, monkeypatch, caplog):
        """Test two un-named chips with the same number of sensors"""

        @staticmethod
        def fake_collect_temperature_sensor_globs():
            return {'/sys/class/hwmon/hwmon0':
                    ('coretemp', [
                        '/sys/class/hwmon/hwmon0/temp2_input',
                        '/sys/class/hwmon/hwmon0/temp5_input',
                        '/sys/class/hwmon/hwmon0/temp3_input',
                        '/sys/class/hwmon/hwmon0/temp1_input',
                        '/sys/class/hwmon/hwmon0/temp4_input']),
                    '/sys/class/hwmon/hwmon1':
                    (None, ['/sys/class/hwmon/hwmon1/temp1_input']),
                    '/sys/class/hwmon/hwmon2':
                    (None, ['/sys/class/hwmon/hwmon2/temp1_input'])}
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_collect_temperature_sensor_globs",
                            fake_collect_temperature_sensor_globs)
        platform = krun.platform.detect_platform(None, None)
        # The duplicate chips should be ignored
        assert platform.temp_sensor_map == {
            'coretemp:5:temp5_input': '/sys/class/hwmon/hwmon0/temp5_input',
            'coretemp:5:temp4_input': '/sys/class/hwmon/hwmon0/temp4_input',
            'coretemp:5:temp3_input': '/sys/class/hwmon/hwmon0/temp3_input',
            'coretemp:5:temp2_input': '/sys/class/hwmon/hwmon0/temp2_input',
            'coretemp:5:temp1_input': '/sys/class/hwmon/hwmon0/temp1_input'
        }
        log = caplog.text()
        assert "Un-named temperature sensor chip found" in log
        assert ("Found duplicate chips named '%s' with 1 temperature sensor(s)"
                % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME) in log

    def test_find_temperature_sensors0004(self, monkeypatch, caplog):
        """Test three un-named chips with the same number of sensors"""

        @staticmethod
        def fake_collect_temperature_sensor_globs():
            return {'/sys/class/hwmon/hwmon0':
                    ('coretemp', [
                        '/sys/class/hwmon/hwmon0/temp2_input',
                        '/sys/class/hwmon/hwmon0/temp5_input',
                        '/sys/class/hwmon/hwmon0/temp3_input',
                        '/sys/class/hwmon/hwmon0/temp1_input',
                        '/sys/class/hwmon/hwmon0/temp4_input']),
                    '/sys/class/hwmon/hwmon1':
                    (None, ['/sys/class/hwmon/hwmon1/temp1_input']),
                    '/sys/class/hwmon/hwmon2':
                    (None, ['/sys/class/hwmon/hwmon2/temp1_input']),
                    '/sys/class/hwmon/hwmon3':
                    (None, ['/sys/class/hwmon/hwmon3/temp1_input'])}
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_collect_temperature_sensor_globs",
                            fake_collect_temperature_sensor_globs)
        platform = krun.platform.detect_platform(None, None)
        # The duplicate chips should be ignored
        assert platform.temp_sensor_map == {
            'coretemp:5:temp5_input': '/sys/class/hwmon/hwmon0/temp5_input',
            'coretemp:5:temp4_input': '/sys/class/hwmon/hwmon0/temp4_input',
            'coretemp:5:temp3_input': '/sys/class/hwmon/hwmon0/temp3_input',
            'coretemp:5:temp2_input': '/sys/class/hwmon/hwmon0/temp2_input',
            'coretemp:5:temp1_input': '/sys/class/hwmon/hwmon0/temp1_input'
        }
        log = caplog.text()
        assert "Un-named temperature sensor chip found" in log
        assert ("Found duplicate chips named '%s' with 1 temperature sensor(s)"
                % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME) in log
        assert ("Found another chip named '%s' with 1 temperature sensor(s)"
                % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME) in log

    def test_find_temperature_sensors0005(self, monkeypatch, caplog):
        """Test two un-named chips with a differing number of sensors works OK"""

        @staticmethod
        def fake_collect_temperature_sensor_globs():
            return {
                # First un-named chip with one sensor
                '/sys/class/hwmon/hwmon0':
                    (None, ['/sys/class/hwmon/hwmon0/temp1_input']),
                # Second with two
                '/sys/class/hwmon/hwmon1':
                    (None, ['/sys/class/hwmon/hwmon1/temp1_input',
                            '/sys/class/hwmon/hwmon1/temp2_input'])
            }
        monkeypatch.setattr(krun.platform.LinuxPlatform,
                            "_collect_temperature_sensor_globs",
                            fake_collect_temperature_sensor_globs)
        platform = krun.platform.detect_platform(None, None)
        assert platform.temp_sensor_map == {
            # First un-named chip
            '%s:1:temp1_input' % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME:
                '/sys/class/hwmon/hwmon0/temp1_input',
            # Second un-named chip
            '%s:2:temp1_input' % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME:
                '/sys/class/hwmon/hwmon1/temp1_input',
            '%s:2:temp2_input' % LinuxPlatform.UNKNOWN_SENSOR_CHIP_NAME:
                '/sys/class/hwmon/hwmon1/temp2_input',
        }
        log = caplog.text()
        assert "Un-named temperature sensor chip found" in log

    def test_isolcpus0001(self, platform, monkeypatch, caplog):
        platform.num_cpus = 4

        def dummy_get_kernel_cmdline():
            return "quiet isolcpus=1,2,3"  # isolcpus not allowed
        monkeypatch.setattr(platform, "_get_kernel_cmdline",
                            dummy_get_kernel_cmdline)

        with pytest.raises(FatalKrunError):
            platform._check_isolcpus()

        find = "isolcpus should not be in the kernel command line"
        assert find in caplog.text()

    def test_is_virtual0001(self, platform):
        """check that virtualisation check doesn't crash"""

        platform.is_virtual()

    def test_check_dmesg_filter0001(self, platform, mock_manifest):
        old_lines = ["START"]  # anchor so krun knows where the changes start
        new_lines = [
            "START",
            # all junk to ignore, and that we have seen in the wild
            "[   76.486320] e1000e: eth0 NIC Link is Down",
            "[  115.052369] e1000e 0000:00:19.0: irq 43 for MSI/MSI-X",
            "[  115.153954] e1000e 0000:00:19.0: irq 43 for MSI/MSI-X",  # twice
            "[  115.154048] IPv6: ADDRCONF(NETDEV_UP): eth0: link is not ready",
            "[  118.714565] e1000e: eth0 NIC Link is Up 1000 Mbps Full Duplex, Flow Control: None",
            "[  118.714594] IPv6: ADDRCONF(NETDEV_CHANGE): eth0: link becomes ready",
            "[    6.672097] r8169 0000:06:00.0 eth0: link up",
            "[  190.178748] r8169 0000:06:00.0 eth0: link down",
            "[  190.178780] r8169 0000:06:00.0 eth0: link down",
            "[  193.276415] r8169 0000:06:00.0 eth0: link up",
            # the graphics card going into powersave
            "[    3.793646] [drm] Enabling RC6 states: RC6 on, RC6p off, RC6pp off",
            # Dell poweredge R330 network coming up
            "[   75.007580] tg3 0000:04:00.0 eth0: Link is up at 1000 Mbps, full duplex",
            "[   75.007582] tg3 0000:04:00.0 eth0: Flow control is off for TX and off for RX",
            "[   75.007583] tg3 0000:04:00.0 eth0: EEE is disabled",
        ]
        assert not platform._check_dmesg_for_changes(
            platform.get_dmesg_whitelist(), old_lines, new_lines, mock_manifest)

    def test_aslr0001(self, platform, caplog):
        # get current ASLR value
        with open(LinuxPlatform.ASLR_FILE, "r") as fh:
            old_val = fh.read().strip()

        # First turn off ASLR
        cmd = "%s sh -c 'echo 0 > %s'" % \
            (platform.change_user_cmd, LinuxPlatform.ASLR_FILE)
        run_shell_cmd(cmd)

        # This should flip it to mode 2
        platform._check_aslr_enabled()
        with open(LinuxPlatform.ASLR_FILE, "r") as fh:
            new_val = fh.read().strip()
        assert new_val == '2'
        assert "Adjust ASLR" in caplog.text()

        # Restore old value
        cmd = "%s sh -c 'echo %s > %s'" % \
            (platform.change_user_cmd, old_val,  LinuxPlatform.ASLR_FILE)
        run_shell_cmd(cmd)
