import bz2  # decent enough compression with Python 2.7 compatibility.
import json
import sys
import time
from subprocess import Popen, PIPE
from logging import error
from krun import LOGFILE_FILENAME_TIME_FORMAT

FLOAT_FORMAT = ".6f"

class ExecutionFailed(Exception):
    pass


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
    """Makes a result file name based upon the config file name."""

    assert config_path.endswith(".krun")
    return config_path[:-5] + "_results.json.bz2"

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


def dump_results(config_file, out_file, all_results, audit):
    """Dump results (and a few other bits) into a bzip2 json file."""
    with open(config_file, "r") as f:
        config_text = f.read()

    to_write = {"config": config_text, "data": all_results, "audit": audit}

    with bz2.BZ2File(out_file, "w") as f:
        f.write(json.dumps(to_write, indent=1, sort_keys=True))


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
        cpuinfo
        packages
        debian_version
        uname
        dmesg
    """
    for key in ["cpuinfo", "packages", "debian_version", "uname"]:
        if (not key in audit0) or (not key in audit1):
            return False
    return ((audit0["cpuinfo"] == audit1["cpuinfo"]) and \
            (audit0["packages"] == audit1["packages"]) and \
            (audit0["debian_version"] == audit1["debian_version"]) and \
            (audit0["uname"] == audit1["uname"]))
