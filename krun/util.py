import json
import os
import re
import select
import shutil
import getpass
from subprocess import Popen, PIPE
from logging import error, debug, info
from bz2 import BZ2File

FLOAT_FORMAT = ".6f"

SELECT_TIMEOUT = 1.0

# Pipe buffer sizes vary. I've seen reports on the Internet ranging from a
# page size (Linux pre-2.6.11) to 64K (Linux in 2015). Ideally we would
# query the pipe for its capacity using F_GETPIPE_SZ, but this is a) not
# portable between UNIXs even, and b) not exposed by Python's fcntl(). For
# now, we use a "reasonable" buffer size. If it is larger than the pipe
# capacity, then no harm done; if it is smaller, then we may do more reads
# than are strictly necessary. In either case we are safe and correct.
PIPE_BUF_SZ = 1024 * 16


DIR = os.path.abspath(os.path.dirname(__file__))

SANITY_CHECK_HEAP_KB = 1024 * 1024  # 1GiB
SANITY_CHECK_STACK_KB = 8192

PLATFORM_SANITY_CHECK_DIR = os.path.join(DIR, "..", "platform_sanity_checks")
VM_SANITY_CHECKS_DIR = os.path.join(DIR, "..", "vm_sanity_checks")


# Keys we expect in each iteration runner's output
EXPECT_JSON_KEYS = set(["wallclock_times", "core_cycle_counts",
                        "aperf_counts", "mperf_counts"])

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

def _run_shell_cmd_start_process(cmd, extra_env):
    debug("execute shell cmd: %s" % cmd)

    env = os.environ.copy()
    if extra_env:
        # Use EnvChangeSet so that we crash out if extra_env conflicts
        # with the current environment.
        from krun.env import EnvChangeSet
        for var, val in extra_env.iteritems():
            ec = EnvChangeSet(var, val)
            ec.apply(env)

    return Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, env=env)

def run_shell_cmd(cmd, failure_fatal=True, extra_env=None):
    p = _run_shell_cmd_start_process(cmd, extra_env)
    stdout, stderr = p.communicate()
    rc = p.wait()
    if failure_fatal and rc != 0:
        msg = "Command failed: '%s'\n" % cmd
        msg += "stdout:\n%s\n" % stdout
        msg += "stderr:\n%s\n" % stderr
        fatal(msg)
    return stdout.strip(), stderr.strip(), rc

def run_shell_cmd_bench(cmd, platform, failure_fatal=True, extra_env=None):
    """ The same as run_shell_cmd, but reads the output of the command more
    carefully, by setting the pipes to unbuffered and using select.
    Requires a platform."""
    process = _run_shell_cmd_start_process(cmd, extra_env)
    res = read_popen_output_carefully(process, platform, print_stderr=False)
    stdout, stderr, rc = res
    if failure_fatal and rc != 0:
        msg = "Command failed: '%s'\n" % cmd
        msg += "stdout:\n%s\n" % stdout
        msg += "stderr:\n%s\n" % stderr
        fatal(msg)
    return res

def run_shell_cmd_list(cmds, failure_fatal=True, extra_env=None):
    """Run a list of shell commands, stopping on first failure."""

    for cmd in cmds:
        _, _, rv = run_shell_cmd(cmd, extra_env=extra_env)
        assert rv == 0

def print_stderr_linewise(info):
    stderr_partial_line = []
    while True:
        d = yield
        # Take what we just read, and any partial line we had from
        # a previous read, and see if we can make full lines.
        # If so, we can print them, otherwise we keep them for
        # the next time around.
        startindex = 0
        while True:
            try:
                nl = d.index("\n", startindex)
            except ValueError:
                stderr_partial_line.append(d[startindex:])
                break  # no newlines
            emit = d[startindex:nl]
            info("stderr: " + "".join(stderr_partial_line) + emit)
            stderr_partial_line = []
            startindex = nl + 1

def read_popen_output_carefully(process, platform, print_stderr=True):
    """ helper function: given a process, read new data whenever it is
    available, to make sure that the process is never blocked when trying to
    write to stdout/stderr. """

    # Get raw OS-level file descriptors and ensure they are unbuffered
    stdout_fd = process.stdout.fileno()
    platform.unbuffer_fd(stdout_fd)
    open_fds = [stdout_fd]

    if process.stderr is None:
        # stderr was redirected to file, forget it
        stderr_fd = None
    else:
        # Krun is consuming stderr
        stderr_fd = process.stderr.fileno()
        open_fds.append(stderr_fd)
        platform.unbuffer_fd(stderr_fd)

    stderr_data, stdout_data = [], []
    if print_stderr:
        stderr_consumer = print_stderr_linewise(info)
        stderr_consumer.next() # start the generator
    else:
        stderr_consumer = None

    while open_fds:
        ready = select.select(open_fds, [], [], SELECT_TIMEOUT)

        if stdout_fd in ready[0]:
            d = os.read(stdout_fd, PIPE_BUF_SZ)
            if d == "":  # EOF
                open_fds.remove(stdout_fd)
            else:
                stdout_data.append(d)

        if stderr_fd in ready[0]:
            d = os.read(stderr_fd, PIPE_BUF_SZ)
            if d == "":  # EOF
                open_fds.remove(stderr_fd)
            else:
                stderr_data.append(d)
                if stderr_consumer is not None:
                    stderr_consumer.send(d)

    # We know stderr and stdout are closed.
    # Now we are just waiting for the process to exit, which may have
    # already happened of course.
    try:
        process.wait()
    except Exception as e:
        fatal("wait() failed on child pipe: %s" % str(e))

    assert process.returncode is not None

    stderr = "".join(stderr_data)
    stdout = "".join(stdout_data)

    return stdout, stderr, process.returncode

def check_and_parse_execution_results(stdout, stderr, rc):
    json_exn = None

    # cset(1) on Linux prints to stdout information about which cpuset a pinned
    # process went to. If this line is present, filter it out.
    stdout = re.sub('^cset: --> last message, executed args into cpuset "/user",'
           ' new pid is: [0-9]+\n', '', stdout)

    try:
        json_data = json.loads(stdout)  # expect a list of floats
    except Exception as e:  # docs don't say what can arise, play safe.
        json_exn = e

    if json_exn or rc != 0:
        # Something went wrong
        rule = 50 * "-"
        err_s = ("Benchmark returned non-zero or emitted invalid JSON.\n")
        if json_exn:
            err_s += "Exception string: %s\n" % str(e)
        err_s += "return code: %d\n" % rc
        err_s += "stdout:\n%s\n%s\n%s\n\n" % (rule, stdout, rule)
        err_s += "stderr:\n%s\n%s\n%s\n" % (rule, stderr, rule)
        raise ExecutionFailed(err_s)

    # Check we have the right keys
    key_set = set(json_data.keys())
    if key_set != EXPECT_JSON_KEYS:
        err_s = "Benchmark emitted unexpected JSON keys\n"
        err_s += "Expected: %s, got: %s" % (EXPECT_JSON_KEYS, key_set)
        raise ExecutionFailed(err_s)

    # Check lengths
    expect_len = len(json_data["wallclock_times"])
    remain_keys = EXPECT_JSON_KEYS - set(["wallclock_times"])
    for key in remain_keys:
        for core_data in json_data[key]:
            if len(core_data) != expect_len:
                err_s = ("Benchmark emitted wrong length '%s' list (%s)" %
                         (key, len(core_data)))
                raise ExecutionFailed(err_s)

    return json_data

def spawn_sanity_check(platform, entry_point, vm_def,
                       check_name, force_dir=None):
    """Run a dummy benchmark which crashes if some property is not satisfied"""

    debug("running '%s' sanity check" % check_name)

    vm_def.set_platform(platform)
    iterations = 1
    param = 666

    stdout, stderr, rc, envlog_filename = \
        vm_def.run_exec(entry_point, check_name, iterations,
                        param, SANITY_CHECK_HEAP_KB, SANITY_CHECK_STACK_KB,
                        force_dir=force_dir, sync_disks=False)
    del_envlog_tempfile(envlog_filename, platform)

    try:
        _ = check_and_parse_execution_results(stdout, stderr, rc)
    except ExecutionFailed as e:
        fatal("%s sanity check failed: %s" % (check_name, e.message))

def assign_platform(config, platform):
    for vm_name, vm_info in config.VMS.items():
        vm_info["vm_def"].set_platform(platform)


def get_session_info(config):
    """Gets information about the session (for --info)

    Overwrites any existing manifest file.

    Separated from print_session_info for ease of testing"""

    from krun.scheduler import ManifestManager
    manifest = ManifestManager.from_config(config)

    return {
        "n_proc_execs": manifest.total_num_execs,
        "n_in_proc_iters": manifest.get_total_in_proc_iters(config),
        "skipped_keys": manifest.skipped_keys,
        "non_skipped_keys": manifest.non_skipped_keys,
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


def get_instr_json_dir(config):
    assert config.filename.endswith(".krun")
    config_base = config.filename[:-5]
    return os.path.join(os.getcwd(), "%s_instr_data" % config_base)


def dump_instr_json(key, exec_num, config, instr_data):
    """Write per-execution instrumentation data to a separate JSON file"""

    instr_json_dir = get_instr_json_dir(config)
    if not os.path.exists(instr_json_dir):
        os.mkdir(instr_json_dir)

    filename = "%s__%s.json.bz2" % (key.replace(":", "__"), exec_num)
    path = os.path.join(instr_json_dir, filename)

    # The directory was checked to be non-existant when the benchmark session
    # started, so it follows that the instrumentation JSON file (each of which
    # is written at most once) should not exist either. If it does, the user
    # did something strange.
    assert not os.path.exists(path)
    with BZ2File(path, "w") as fh:
        fh.write(json.dumps(instr_data))


def get_envlog_dir(config):
    assert config.filename.endswith(".krun")
    config_base = config.filename[:-5]
    return os.path.join(os.getcwd(), "%s_envlogs" % config_base)


def stash_envlog(tmp_filename, config, platform, key, exec_num):
    """Move the environment log file out of /tmp into the experiment dir"""

    envlog_dir = get_envlog_dir(config)
    if not os.path.exists(envlog_dir):
        os.mkdir(envlog_dir)

    new_filename = "%s__%s.env" % (key.replace(":", "__"), exec_num)
    new_path = os.path.join(envlog_dir, new_filename)

    # Similarly to dump_instr_json(), the file cannot exist at this point
    assert not os.path.exists(new_path)
    shutil.copyfile(tmp_filename, new_path)
    del_envlog_tempfile(tmp_filename, platform)


def del_envlog_tempfile(filename, platform):
    """Clear away the old file"""

    if not os.path.exists(filename):  # some tests skip creation
        return

    if platform.no_user_change:
        os.unlink(filename)
    else:
        # Is owned by BENCHMARK_USER so we can't directly remove the file
        from krun.vm_defs import BENCHMARK_USER
        args = platform.change_user_args(BENCHMARK_USER) + ["rm", filename]
        run_shell_cmd(" ".join(args))
