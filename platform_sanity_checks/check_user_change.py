# Fake benchmark that checks we are running as the krun user.

import os
import pwd

KRUN_USER = "krun"


def run_iter(n, _):
    env_user = os.environ.get("USER", None)
    syscall_user = pwd.getpwuid(os.geteuid())[0]

    ok = True

    if env_user != KRUN_USER:
        ok = False

    if syscall_user != KRUN_USER:
        ok = False

    if not ok:
        raise RuntimeError(
            "krun user check failed: env=%s, getuid()=%s, expect=%s" %
            (env_user, syscall_user, KRUN_USER))

    return 0
