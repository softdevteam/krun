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

from krun.platform import BasePlatform
from krun.config import Config
from krun.mail import Mailer
import pytest


class MockMailer(Mailer):
    def __init__(self, recipients=None, max_mails=5):
        Mailer.__init__(self, recipients, max_mails)
        self.sent = []  # cache here instead of sending for real
        self.hostname = "tests.suite"
        self.short_hostname = self.hostname.split(".")[0]

    def _sendmail(self, msg):
        self.sent.append(msg)


@pytest.fixture
def mock_mailer():
    return MockMailer()


class MockPlatform(BasePlatform):
    """Pretends to be a Platform instance."""

    CHANGE_USER_CMD = ""

    def __init__(self, mailer, config):
        BasePlatform.__init__(self, mailer, config)
        self.mailer = mailer
        self.audit = dict()
        self.num_cpus = 0
        self.num_per_core_measurements = 0
        self.no_user_change = True
        self.temp_sensors = []

    def default_dmesg_whitelist(self):
        return []

    def pin_process_args(self):
        return []

    def change_scheduler_args(self):
        return []

    def check_dmesg_for_changes(self, manifest):
        pass

    def CHANGE_USER_CMD(self):
        pass

    def take_temperature_readings(self):
        return {}

    def check_preliminaries(self):
        pass

    def unbuffer_fd(self, fd):
        pass

    def adjust_env_cmd(self, env_dct):
        return []

    def FORCE_LIBRARY_PATH_ENV_NAME(self):
        pass

    def collect_audit(self):
        self.audit["uname"] = "MockPlatform"

    def bench_cmdline_adjust(self, args, env_dct):
        return args

    def change_user_args(self, user="root"):
        return ["sudo"]

    def process_priority_args(self):
        return []

    def get_reboot_cmd(self):
        assert False  # tests should never try to reboot

    def _change_user_args(self):
        return []

    def _save_power(self):
        pass

    def _collect_dmesg_lines(self):
        return []

    def bench_env_changes(args, env_dct):
        return []

    def sanity_checks(self):
        pass

    def sync_disks(self):
        pass

    def find_temperature_sensors(self):
        return []

    def is_virtual(self):
        return False

    def make_fresh_krun_user(self):
        pass

    def get_num_temperature_sensors(self):
        return 1

    def _read_throttle_counts(self):
        return {}


@pytest.fixture
def mock_platform():
    return MockPlatform(MockMailer(), Config())


class MockManifestManager(object):
    """For tests which need a manifest, but you don't want a file on-disk or a
    config instance"""

    def __init__(self):
        self.num_mails_sent = 0

@pytest.fixture
def mock_manifest():
    return MockManifestManager()
