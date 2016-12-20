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

    def pin_process_args(self):
        return []

    def change_scheduler_args(self):
        return []

    def check_dmesg_for_changes(self, mock_platform):
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
