import json
import sys
from subprocess import Popen, PIPE
from logging import error

FLOAT_FORMAT = ".6f"

class ExecutionFailed(Exception):
    pass


def fatal(msg):
    error(msg)
    sys.exit(1)


def log_and_mail(mailer, log_fn, subject, msg, exit=False, bypass_limiter=False):
    log_fn(msg)
    mailer.send(subject, msg, bypass_limiter)
    if exit:
        sys.exit(1)


def format_raw_exec_results(exec_data):
    """Formats the raw results from an iterations runner.
    For now, this rounds the results to a fixed number of decimal points.
    This is needed because every language has its own rules WRT floating point
    precision."""

    return [float(format(x, FLOAT_FORMAT)) for x in exec_data]


def run_shell_cmd(cmd, failure_fatal=True):
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    stdout, stderr = p.communicate()
    rc = p.wait()
    if failure_fatal and rc != 0:
        fatal("Shell command failed: '%s'" % cmd)
    return stdout.strip(), stderr.strip(), rc


def check_and_parse_execution_results(stdout, stderr, rc):
    json_exn = None
    try:
        iterations_results = json.loads(stdout)  # expect a list of floats
    except Exception as e:  # docs don't say what can arise, play safe.
        json_exn = e

    if json_exn or rc != 0:
        # Something went wrong
        rule = 50 * "-"
        err_s = ("Benchmark returned non-zero or didn't emit JSON list. ")
        if json_exn:
            err_s += "Exception string: %s\n" % str(e)
        err_s += "return code: %d\n" % rc
        err_s += "stdout:\n%s\n%s\n%s\n\n" % (rule, stdout, rule)
        err_s += "stderr:\n%s\n%s\n%s\n" % (rule, stderr, rule)
        raise ExecutionFailed(err_s)

    return iterations_results


def audits_same_platform(audit0, audit1):
    """Check whether two platform audits are from identical machines.
    A machine audit is a dictionary with the following keys:

        * cpuinfo (Linux only)
        * packages (Debian-based systems only)
        * debian_version (Debian-based systems only)
        * uname (all platforms)
        * dmesg (all platforms)

    Platform information may be Unicode.
    """
    if ("uname" not in audit0) or ("uname" not in audit1):
        return False
    return audit0["uname"] == audit1["uname"]
