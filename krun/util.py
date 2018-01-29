# Copyright (c) 2017 King's College London
# created by the Software Development Team <http://soft-dev.org/>
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or
# data (collectively the "Software"), free of charge and under any and all
# copyright rights in the Software, and any and all patent rights owned or
# freely licensable by each licensor hereunder covering either (i) the
# unmodified Software as contributed to or provided by such licensor, or (ii)
# the Larger Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
# one is included with the Software (each a "Larger Work" to which the Software
# is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright
# notice and either this complete permission notice or at a minimum a reference
# to the UPL must be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import os
import re
import select
import shutil
import sys
import subprocess
import pwd
import grp
import getpass
from subprocess import Popen, PIPE
from logging import error, debug, info, warn, root as root_logger
from bz2 import BZ2File
from krun.amperf import check_amperf_ratios

FLOAT_FORMAT = ".6f"
INSTR_STDERR_TAIL = 100
SELECT_TIMEOUT = 1.0

# Pipe buffer sizes vary. I've seen reports on the Internet ranging from a
# page size (Linux pre-2.6.11) to 64K (Linux in 2015). Ideally we would
# query the pipe for its capacity using F_GETPIPE_SZ, but this is a) not
# portable between UNIXs even, and b) not exposed by Python's fcntl(). For
# now, we use a "reasonable" buffer size. If it is larger than the pipe
# capacity, then no harm done; if it is smaller, then we may do more reads
# than are strictly necessary. In either case we are safe and correct.
PIPE_BUF_SZ = 1024 * 16

from stat import S_IRUSR, S_IWUSR, S_IRGRP, S_IWGRP, S_IXUSR, S_IXGRP, S_IROTH, S_IXOTH
INSTR_DIR_MODE = S_IRUSR | S_IWUSR | S_IXUSR \
    | S_IRGRP | S_IWGRP | S_IXGRP \
    | S_IROTH | S_IXOTH

DIR = os.path.abspath(os.path.dirname(__file__))

SANITY_CHECK_HEAP_KB = 1024 * 1024  # 1GiB
SANITY_CHECK_STACK_KB = 8192

PLATFORM_SANITY_CHECK_DIR = os.path.join(DIR, "..", "platform_sanity_checks")
VM_SANITY_CHECKS_DIR = os.path.join(DIR, "..", "vm_sanity_checks")

BAD_AMPERF_SUBJECT = "Bad APERF/MPERF ratio(s) detected"

# Keys we expect in each iteration runner's output
EXPECT_JSON_KEYS = set(["wallclock_times", "core_cycle_counts",
                        "aperf_counts", "mperf_counts"])

class ExecutionFailed(Exception):
    pass


class RerunExecution(Exception):
    pass


class FatalKrunError(Exception):
    pass

def fatal(msg):
    error(msg)

    # We raise, then later this is trapped in an attempt to run the user's
    # post-session commands. The message is stashed inside the exception so
    # that we can send an email indicating the problem later.
    raise FatalKrunError(msg)


def log_and_mail(mailer, log_fn, subject, msg, exit=False,
                 bypass_limiter=False, manifest=None):
    log_fn(msg)
    mailer.send(subject, msg, bypass_limiter=bypass_limiter, manifest=manifest)
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


def check_and_parse_execution_results(stdout, stderr, rc, config,
                                      sanity_check=False, instrument=False):
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

        # In instrumentation mode, stderr will have been written to disk for
        # parsing. Read the last INSTR_STDERR_TAIL lines back (it may be huge)
        # so as to offer the user at least something relating to the error.
        if instrument:
            from krun.vm_defs import INST_STDERR_FILE
            num_stderr_lines = 0
            with open(INST_STDERR_FILE) as fh:
                for _ in fh:
                    num_stderr_lines += 1
                fh.seek(0, 0)  # rewind file
                stderr_lines = []
                for line_num, line in enumerate(fh):
                    if line_num >= num_stderr_lines - INSTR_STDERR_TAIL:
                        stderr_lines.append(line)
            stderr = "".join(stderr_lines)

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

    # Check the CPU did not clock down, if the platform supports APERF/MPERF
    if config.AMPERF_RATIO_BOUNDS and not sanity_check:
        if json_data["aperf_counts"] == []:
            warn("platform does not support APERF and MPERF counts."
                 " Not checking ratios.")
        else:
            amperf_results = check_amperf_ratios(json_data["aperf_counts"],
                                                 json_data["mperf_counts"],
                                                 json_data["wallclock_times"],
                                                 config.AMPERF_BUSY_THRESHOLD,
                                                 config.AMPERF_RATIO_BOUNDS)
            error_lines = []
            for core_idx, ratios in enumerate(amperf_results):
                if not ratios.ok():
                    if not error_lines:
                        # First badness, make a header
                        error_lines.append("APERF/MPERF ratio badness detected")
                    for typ in ratios.violations.keys():
                        for iter_idx in ratios.violations[typ]:
                            error_lines.append(
                                "  in_proc_iter=%s, core=%s, type=%s, ratio=%s" %
                            (iter_idx, core_idx, typ, ratios.vals[iter_idx]))
            if error_lines:
                error_lines.append("\nThe process execution will be retried"
                                   " until the ratios are OK.")
                raise RerunExecution("\n".join(error_lines))
    return json_data

def spawn_sanity_check(platform, entry_point, vm_def,
                       check_name, force_dir=None):
    """Run a dummy benchmark which crashes if some property is not satisfied"""

    debug("running '%s' sanity check" % check_name)

    vm_def.set_platform(platform)
    iterations = 1
    param = 666

    key = "%s:sanity:default-sanity" % check_name
    stdout, stderr, rc, envlog_filename = \
        vm_def.run_exec(entry_point, iterations,
                        param, SANITY_CHECK_HEAP_KB, SANITY_CHECK_STACK_KB,
                        key, 0, force_dir=force_dir, sync_disks=False)
    del_envlog_tempfile(envlog_filename, platform)

    try:
        _ = check_and_parse_execution_results(stdout, stderr, rc,
                                              platform.config,
                                              sanity_check=True)
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
    from krun.platform import detect_platform
    platform = detect_platform(None, config)
    manifest = ManifestManager(config, platform, new_file=True)

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


def make_instr_dir(config):
    dir = get_instr_json_dir(config)
    debug("making instrumentation dir: %s" % dir)
    os.mkdir(dir)


def set_instr_dir_perms(config, platform):
    """Grant the Krun user write access to the instrumentation dir.

    Sadly this has to be done as root as there is no guarantee that the initial
    user is in the krun user's group."""

    from krun.vm_defs import BENCHMARK_USER
    group = grp.getgrnam(BENCHMARK_USER).gr_name
    user = pwd.getpwnam(getpass.getuser()).pw_name

    from krun import util
    path = util.get_instr_json_dir(config)

    args = platform.change_user_args()
    args.extend(["chown", "%s:%s" % (user, group), path])
    run_shell_cmd(" ".join(args))

    os.chmod(path, INSTR_DIR_MODE)


def dump_instr_json(key, exec_num, config, instr_data):
    """Write per-execution instrumentation data to a separate JSON file.

    Assumes the instrumentation directory exists."""

    filename = "%s__%s.json.bz2" % (key.replace(":", "__"), exec_num)
    path = os.path.join(get_instr_json_dir(config), filename)

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


def logging_done():
    """Close all logging file descriptors"""

    for handler in root_logger.handlers[:]:
        debug("close logging handler: %s" % handler)
        handler.close()
        root_logger.removeHandler(handler)


def _do_reboot(platform):
    """Really do the reboot, separate for testing"""

    if not platform.hardware_reboots:
        warn("SIMULATED: reboot (--hardware-reboots is OFF)")
        args = sys.argv
        debug("Simulated reboot with args: " + " ".join(args))
        logging_done()
        os.execv(args[0], args)  # replace myself
        assert False  # unreachable
    else:
        # No need to close logging fds in the case of a real reboot. This also
        # allows the fatal() below to log in case of failure.
        rc = subprocess.call(platform.get_reboot_cmd())
        if rc != 0:
            fatal("Failed to reboot with: %s" % platform.get_reboot_cmd())
        else:
            debug("hard exit")
            # Use _exit() to stop without raising SystemExit, otherwise more
            # Python code may run.
            os._exit(0)


def reboot(manifest, platform, update_count=True):
    """Check reboot count and reboot"""

    expected_reboots = manifest.total_num_execs
    if update_count:
        manifest.update_num_reboots()
        debug("about to execute reboot: %g, expecting %g in total." %
              (manifest.num_reboots, expected_reboots))

    # Check for a boot loop
    if manifest.num_reboots > expected_reboots:
        fatal(("HALTING now to prevent an infinite reboot loop: " +
                    "INVARIANT num_reboots <= num_jobs violated. " +
                    "Krun was about to execute reboot number: %g. " +
                    "%g jobs have been completed, %g are left to go.") %
                   (manifest.num_reboots, manifest.next_exec_idx,
                    manifest.num_execs_left))
    _do_reboot(platform)


def check_audit_unchanged(results, platform):
    """Crash out if the audit in the result doesn't match the one in the
    platform"""

    from krun.audit import Audit
    if Audit(platform.audit) != results.audit:
        error_msg = (
            "You have asked Krun to resume an interrupted benchmark. "
            "This is only valid if the machine you are using is "
            "identical to the one on which the last results were "
            "gathered, which is not the case.")
        fatal(error_msg)


def daemonise():
    """Daemonise Krun"""

    debug("daemonising...")
    try:
        pid = os.fork()
    except OSError:
        fatal("failed to daemonise: first fork")

    if pid != 0:
        # parent
        os._exit(0)

    os.setsid()
    try:
        pid = os.fork()
    except OSError:
        fatal("failed to daemonise: second fork")

    if pid != 0:
        # parent
        os._exit(0)

    # Redirect stdin/stdout/stderr to /dev/null
    null = os.open("/dev/null", os.O_RDWR)
    for fd in xrange(3):
        # Since these fds will be in-use, dup2 will close them first
        os.dup2(null, fd)
