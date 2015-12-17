import json
import sys
import os
from subprocess import Popen, PIPE
from logging import error, debug

FLOAT_FORMAT = ".6f"

DIR = os.path.abspath(os.path.dirname(__file__))

SANITY_CHECK_HEAP_KB = 1024 * 1024  # 1GB
SANITY_CHECK_STACK_KB = 8192

PLATFORM_SANITY_CHECK_DIR = os.path.join(DIR, "..", "platform_sanity_checks")
VM_SANITY_CHECKS_DIR = os.path.join(DIR, "..", "vm_sanity_checks")

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

def spawn_sanity_check(platform, entry_point, vm_def,
                       check_name, force_dir=None):
    """Run a dummy benchmark which crashes if some property is not satisfied"""

    debug("running '%s' sanity check" % check_name)

    vm_def.set_platform(platform)
    iterations = 1
    param = 666

    stdout, stderr, rc = \
        vm_def.run_exec(entry_point, check_name, iterations,
                        param, SANITY_CHECK_HEAP_KB, SANITY_CHECK_STACK_KB,
                        force_dir=force_dir)

    try:
        _ = check_and_parse_execution_results(stdout, stderr, rc)
    except ExecutionFailed as e:
        fatal("%s sanity check failed: %s" % (check_name, e.message))

def assign_platform(config, platform):
    for vm_name, vm_info in config.VMS.items():
        vm_info["vm_def"].set_platform(platform)
