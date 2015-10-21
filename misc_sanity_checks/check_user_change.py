# Fake benchmark that checks we are running as the krun user.

import os
import pwd

KRUN_USER = "krun"


def run_iter(n):
    env_user = os.environ["USER"]
    syscall_user = pwd.getpwuid(os.geteuid())[0]

    ok = env_user == syscall_user == KRUN_USER

    if not ok:
        raise RuntimeError(
            "krun user check failed: env=%s, getuid()=%s, expect=%s" %
            (env_user, syscall_user, KRUN_USER))
