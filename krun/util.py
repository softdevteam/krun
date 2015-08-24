import sys
import time
from subprocess import Popen, PIPE
from logging import error
from krun import LOGFILE_FILENAME_TIME_FORMAT

def should_skip(config, this_key):
    skips = config["SKIP"]

    for skip_key in skips:
        skip_elems = skip_key.split(":")
        this_elems = this_key.split(":")

        # should be triples of: bench * vm * variant
        assert len(skip_elems) == 3 and len(this_elems) == 3

        for i in range(3):
            if skip_elems[i] == "*":
                this_elems[i] = "*"

        if skip_elems == this_elems:
            return True # skip

    return False


def read_config(path):
    assert path.endswith(".krun")
    dct = {}
    try:
        execfile(path, dct)
    except Exception as e:
        error("error importing config file:\n%s" % str(e))
        raise

    return dct


def output_name(config_path):
    assert config_path.endswith(".krun")
    return config_path[:-5] + "_results.json"

def log_name(config_path):
    assert config_path.endswith(".krun")
    return config_path[:-5] + "_%s.log" % \
        time.strftime(LOGFILE_FILENAME_TIME_FORMAT)

def fatal(msg):
    error(msg)
    sys.exit(1)


def log_and_mail(mailer, log_fn, subject, msg, exit=False, bypass_limiter=False):
    log_fn(msg)
    mailer.send(subject, msg, bypass_limiter)
    if exit:
        sys.exit(1)

def run_shell_cmd(cmd, failure_fatal=True):
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    rc = p.wait()
    if failure_fatal and rc != 0:
        fatal("Shell command failed: '%s'" % cmd)
    return stdout.strip(), stderr.strip(), rc
