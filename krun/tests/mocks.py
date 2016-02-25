from krun.platform import BasePlatform


class MockMailer(object):
    def __init__(self, recipients=[], max_mails=2):
        self.recipients = recipients
        self.max_mails = max_mails

    def send(self, subject, msg, bypass_limiter):
        assert True  # Confirm a mail will be sent.
        return None


class MockPlatform(BasePlatform):
    """Pretends to be a Platform instance."""

    CHANGE_USER_CMD = ""

    def __init__(self, mailer):
        BasePlatform.__init__(self, mailer)
        self.mailer = mailer
        self.audit = dict()
        self.num_cpus = 0
        self.developer_mode = False

    def check_dmesg_for_changes(self):
        pass

    def wait_until_cpu_cool(self):
        pass

    def CHANGE_USER_CMD(self):
        pass

    def take_temperature_readings(self):
        pass

    def has_cooled(self):
        return True, None  # pretend we cooled down OK

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
        return "sudo"

    def process_priority_args(self):
        return []

    def get_reboot_cmd(self):
        return ""

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
