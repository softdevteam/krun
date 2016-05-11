import json
import os
from subprocess import Popen, PIPE
from logging import error, debug, info

FLOAT_FORMAT = ".6f"

DIR = os.path.abspath(os.path.dirname(__file__))

SANITY_CHECK_HEAP_KB = 1024 * 1024  # 1GiB
SANITY_CHECK_STACK_KB = 8192

PLATFORM_SANITY_CHECK_DIR = os.path.join(DIR, "..", "platform_sanity_checks")
VM_SANITY_CHECKS_DIR = os.path.join(DIR, "..", "vm_sanity_checks")

class ExecutionFailed(Exception):
    pass


class FatalKrunError(Exception):
    pass

def fatal(msg):
    error(msg)

    # We raise, then later this is trapped in an attempt to run the user's
    # post-session commands. The message is stashed inside the exception so
    # that we can send an email indicating the problem later.
    raise FatalKrunError(msg)


def log_and_mail(mailer, log_fn, subject, msg, exit=False, bypass_limiter=False):
    log_fn(msg)
    mailer.send(subject, msg, bypass_limiter)
    if exit:
        raise FatalKrunError()  # causes post-session commands to run


def format_raw_exec_results(exec_data):
    """Formats the raw results from an iterations runner.
    For now, this rounds the results to a fixed number of decimal points.
    This is needed because every language has its own rules WRT floating point
    precision."""

    return [float(format(x, FLOAT_FORMAT)) for x in exec_data]


def run_shell_cmd(cmd, failure_fatal=True, extra_env=None):
    debug("execute shell cmd: %s" % cmd)

    env = os.environ.copy()
    if extra_env:
        # Use EnvChangeSet so that we crash out if extra_env conflicts
        # with the current environment.
        from krun.env import EnvChangeSet
        for var, val in extra_env.iteritems():
            ec = EnvChangeSet(var, val)
            ec.apply(env)

    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, env=env)
    stdout, stderr = p.communicate()
    rc = p.wait()
    if failure_fatal and rc != 0:
        msg = "Command failed: '%s'\n" % cmd
        msg += "stdout:\n%s\n" % stdout
        msg += "stderr:\n%s\n" % stderr
        fatal(msg)
    return stdout.strip(), stderr.strip(), rc


def run_shell_cmd_list(cmds, failure_fatal=True, extra_env=None):
    """Run a list of shell commands, stopping on first failure."""

    for cmd in cmds:
        _, _, rv = run_shell_cmd(cmd, extra_env=extra_env)
        assert rv == 0

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
                        force_dir=force_dir, sync_disks=False)

    try:
        _ = check_and_parse_execution_results(stdout, stderr, rc)
    except ExecutionFailed as e:
        fatal("%s sanity check failed: %s" % (check_name, e.message))

def assign_platform(config, platform):
    for vm_name, vm_info in config.VMS.items():
        vm_info["vm_def"].set_platform(platform)


def get_session_info(config):
    """Gets information about the session (for --info)

    Separated from print_session_info for ease of testing"""

    from krun.scheduler import ScheduleEmpty, ExecutionScheduler
    from krun.platform import detect_platform

    platform = detect_platform(None, config)
    sched = ExecutionScheduler(config, None, platform)
    non_skipped_keys, skipped_keys = sched.build_schedule()

    n_proc_execs = 0
    n_in_proc_iters = 0

    while True:
        try:
            job = sched.next_job()
        except ScheduleEmpty:
            break

        n_proc_execs += 1
        n_in_proc_iters += job.vm_info["n_iterations"]

    return {
        "n_proc_execs": n_proc_execs,
        "n_in_proc_iters": n_in_proc_iters,
        "skipped_keys": skipped_keys,
        "non_skipped_keys": non_skipped_keys,
    }


def print_session_info(config):
    """Prints information about the session (for --info)"""

    info = get_session_info(config)

    print("\nSession Info")
    print("============\n")

    print("Counts:")
    print("  Total process executions:    %10d" % info["n_proc_execs"])
    print("  Total in-process iterations: %10d" % info["n_in_proc_iters"])
    print("  Total unique benchmark keys: %10d\n"
          % len(info["non_skipped_keys"]))

    print("Non-skipped keys:")
    if len(info["non_skipped_keys"]) > 0:
        for k in info["non_skipped_keys"]:
            print("  %s" % k)
    else:
        print("  All keys skipped!")
    print("")

    print("Skipped keys:")
    if len(info["skipped_keys"]) > 0:
        for k in info["skipped_keys"]:
            print("  %s" % k)
    else:
        print("  No keys skipped")


def make_heat():
    """A loop which spins, attempting to make heat.

    Used when the CPU is too cool to run a benchmark."""

    # Waste cycles with this loop. At the time of writing PyPy is unable to
    # optimise this away. Heat is a consequence.
    j = 0
    for i in xrange(10000000):
        j += 1
    assert j == 10000000


def get_git_version():
    """Ask the krun checkout for its version. This assumes that Krun is run
    from a git clone. If we decide to package this into (e.g.) PyPI at a later
    date, then we would have to re-think this.
    """

    from distutils.spawn import find_executable
    if not find_executable("git"):
        fatal("git not found in ${PATH}. Please install git.")

    out, err, code = \
        run_shell_cmd("sh -c 'cd %s && git rev-parse --verify HEAD'" % DIR)

    return out.strip()  # returns the hash


def strip_results(config, key_spec):
    from krun.platform import detect_platform
    from krun.results import Results

    platform = detect_platform(None)
    results = Results(config, platform,
                      results_file=config.results_filename())
    n_removed = results.strip_results(key_spec)
    if n_removed > 0:
        results.write_to_file()
    info("Removed %d result keys" % n_removed)
