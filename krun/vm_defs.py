import subprocess
import os
import select
import fnmatch
import json
import re
from abc import ABCMeta, abstractmethod

from logging import info, debug, warn
from krun import EntryPoint
from krun.util import fatal, spawn_sanity_check, VM_SANITY_CHECKS_DIR
from krun.env import EnvChangeAppend, EnvChangeSet, EnvChange
from krun.util import SANITY_CHECK_HEAP_KB
from distutils.spawn import find_executable

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = os.path.abspath(os.path.join(os.getcwd(), "benchmarks"))
BENCHMARK_USER = "krun"  # user is expected to have made this
INST_STDERR_FILE = "/tmp/krun.stderr"

# Pipe buffer sizes vary. I've seen reports on the Internet ranging from a
# page size (Linux pre-2.6.11) to 64K (Linux in 2015). Ideally we would
# query the pipe for its capacity using F_GETPIPE_SZ, but this is a) not
# portable between UNIXs even, and b) not exposed by Python's fcntl(). For
# now, we use a "reasonable" buffer size. If it is larger than the pipe
# capacity, then no harm done; if it is smaller, then we may do more reads
# than are strictly necessary. In either case we are safe and correct.
PIPE_BUF_SZ = 1024 * 16

SELECT_TIMEOUT = 1.0

WRAPPER_SCRIPT = os.sep + os.path.join("tmp", "krun_wrapper.dash")
DASH = find_executable("dash")
if DASH is None:
    fatal("dash shell not found")

INSTRUMENTATION_END_PROC_ITER_PREFIX = "@@@ END_IN_PROC_ITER:"


# !!!
# Don't mutate any lists passed down from the user's config file!
# !!!


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


class BaseVMDef(object):
    __metaclass__ = ABCMeta

    def __init__(self, iterations_runner, env=None, instrument=False):
        self.iterations_runner = iterations_runner

        # List of EnvChange instances to apply prior to each experiment.
        # These should be benchmark agnostic. Look elsewhere for
        # environment changes specific to a benchmark.
        self.common_env_changes = []

        # The user can pass in a dict to influence the environment.
        #
        # These variables are *prepended* to any coinsiding environment that
        # Krun has set to run benchmarks. E.g. If Krun wants to set
        # LD_LIBRARY_PATH=/opt/pypy/pypy/goal, and the user passes down
        # {"LD_LIBRARY_PATH": "/wibble/lib"}, the resulting environment is
        # LD_LIBRARY_PATH=/wibble/lib:/opt/pypy/pypy/goal
        #
        # This is useful, for example, if the user built their own GCC
        # and needs to force the LD_LIBRARY_PATH.
        if env is not None:
            if not isinstance(env, dict):
                fatal("'env' argument for VM defs should be a dict")
            for k, v in env.iteritems():
                self.add_env_change(EnvChangeAppend(k, v))

        # tempting as it is to add a self.vm_path, we don't. If we were to add
        # natively compiled languages, then there is no "VM" to speak of.

        # These are set later
        self.platform = None
        self.config = None

        # Do not execute the benchmark program
        # (useful for testing configurations.).
        self.dry_run = False

        self.instrument = instrument

    def _get_benchmark_path(self, benchmark, entry_point, force_dir=None):
        if force_dir is not None:
            # Forcing a directory! Used for sanity checks.
            return os.path.join(force_dir, entry_point.target)
        else:
            if entry_point.subdir is not None:
                return os.path.join(
                    BENCHMARKS_DIR, benchmark, entry_point.subdir,
                    entry_point.target)
            else:
                return os.path.join(
                    BENCHMARKS_DIR, benchmark, entry_point.target)

    def set_platform(self, platform):
        self.platform = platform
        self.config = platform.config

    def add_env_change(self, change):
        self.common_env_changes.append(change)

    def apply_env_changes(self, bench_env_changes, env_dct):
        """Applies both VM and benchmark specific environment to env_dct"""

        assert isinstance(bench_env_changes, list)

        # Apply vm specific environment changes
        EnvChange.apply_all(self.common_env_changes, env_dct)

        # Apply benchmark specific environment changes
        EnvChange.apply_all(bench_env_changes, env_dct)

    @abstractmethod
    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        pass

    @staticmethod
    def make_wrapper_script(args, heap_lim_k, stack_lim_k):
        """Make lines for the wrapper script.
        Separate for testing purposes"""

        return [
            "#!%s" % DASH,
            "ulimit -d %s || exit $?" % heap_lim_k,
            "ulimit -s %s || exit $?" % stack_lim_k,
            " ".join(args),
            "exit $?",
        ]

    def _run_exec(self, args, heap_lim_k, stack_lim_k, bench_env_changes=None,
                  sync_disks=True):
        """ Deals with actually shelling out """

        if bench_env_changes is None:
            bench_env_changes = []

        # Environment *after* user change.
        # Starts empty, but user change command (i.e. sudo) may introduce some.
        new_user_env = {}

        # Apply envs
        self.apply_env_changes(bench_env_changes, new_user_env)

        # Apply platform specific argument transformations.
        args = self.platform.bench_cmdline_adjust(args, new_user_env)

        # Tack on the debug flag: 0 or 1
        import logging
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            args.append("1")
        else:
            args.append("0")

        # Tack on the instrumentation flag
        # All runners accept this flag, even if instrumentation is not
        # implemented for the VM in question.
        stderr_filename = None
        if self.instrument:
            args.append("1")
            stderr_filename = INST_STDERR_FILE
        else:
            args.append("0")

        if self.dry_run:
            warn("SIMULATED: Benchmark process execution (--dryrun)")
            return ("", "", 0)

        # We write out a wrapper script whose job is to enforce ulimits
        # before executing the VM.
        debug("Writing out wrapper script to %s" % WRAPPER_SCRIPT)
        lines = BaseVMDef.make_wrapper_script(args, heap_lim_k, stack_lim_k)
        with open(WRAPPER_SCRIPT, "w") as fh:
            for line in lines:
                fh.write(line + "\n")

        debug("Wrapper script:\n%s" % ("\n".join(lines)))

        wrapper_args = self._wrapper_args()
        debug("Execute wrapper: %s" % (" ".join(wrapper_args)))

        # Do an OS-level sync. Forces pending writes on to the physical disk.
        # We do this in an attempt to prevent disk commits happening during
        # benchmarking.
        if sync_disks:
            self.platform.sync_disks()

        return self._run_exec_popen(wrapper_args, stderr_filename)

    # separate for testing
    def _wrapper_args(self):
        """Build arguments used to run the wrapper script"""

        wrapper_args = self.platform.change_user_args("root") + \
            self.platform.process_priority_args()

        if self.config.ENABLE_PINNING:
                wrapper_args += self.platform.pin_process_args()

        if self.platform.no_user_change:
            warn("Not changing user (--no-change-user)")
        else:
            wrapper_args += self.platform.change_user_args(BENCHMARK_USER)

        wrapper_args += [DASH, WRAPPER_SCRIPT]

        return wrapper_args

    # separate for testing purposes
    def _run_exec_popen(self, args, stderr_filename=None):
        """popen to the wrapper script

        arguments:
          args: list of arguments to pass to popen().
          stderr_filename: if specified (as a string), write stderr to this filename.
        """

        # We pass the empty environment dict here.
        # This is the *outer* environment that the current user will invoke the
        # command with. Command line arguments will have been appended *inside*
        # to adjust the new user's environment once the user switch has
        # occurred.
        p = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={})

        if stderr_filename is not None:
            stderr_file = open(stderr_filename, "w")
        else:
            stderr_file = None

        rv = self._run_exec_capture(p, stderr_file)

        if stderr_filename is not None:
            stderr_file.close()

        os.unlink(WRAPPER_SCRIPT)
        return rv

    def _run_exec_capture(self, child_pipe, stderr_file=None):
        """Allows the subprocess (whose pipes we have handles on) to run
        to completion. We print stderr as it arrives.

        arguments:
          child_pipe: pipe to read from.
          stderr_file: if not None, a file handle to write stderr to.

        Returns a triple: stderr, stdout and the returncode.

        If a stderr_file is specified, standard error goes to the file instead
        of to the first element of the return value. In this case, the stderr
        element will be the empty string."""

        # Get raw OS-level file descriptors
        stderr_fd, stdout_fd = \
            child_pipe.stderr.fileno(), child_pipe.stdout.fileno()

        # Ensure both fds are unbuffered.
        # stderr should already be, but it doesn't hurt to force it.
        for f in [stderr_fd, stdout_fd]:
            self.platform.unbuffer_fd(f)

        stderr_data, stdout_data = [], []
        stderr_consumer = print_stderr_linewise(info)
        stderr_consumer.next() # start the generator

        open_fds = [stderr_fd, stdout_fd]
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
                    if stderr_file is None:
                        stderr_data.append(d)
                    else:
                        stderr_file.write(d)
                    stderr_consumer.send(d)
        # We know stderr and stdout are closed.
        # Now we are just waiting for the process to exit, which may have
        # already happened of course.
        try:
            child_pipe.wait()
        except Exception as e:
            fatal("wait() failed on child pipe: %s" % str(e))

        assert child_pipe.returncode is not None

        stderr = "".join(stderr_data)
        stdout = "".join(stdout_data)

        return stdout, stderr, child_pipe.returncode

    def sanity_checks(self):
        pass

    @abstractmethod
    def check_benchmark_files(self, benchmark, entry_point):
        pass

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    @abstractmethod
    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def get_instrumentation_data(self):
        with open(INST_STDERR_FILE, "r") as fh:
            return self.parse_instrumentation_stderr_file(fh)


class NativeCodeVMDef(BaseVMDef):
    """Not really a "VM definition" at all. Runs native code."""

    def __init__(self, env=None):
        iter_runner = os.path.join(ITERATIONS_RUNNER_DIR,
                                   "iterations_runner_c")
        BaseVMDef.__init__(self, iter_runner, env=env)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        benchmark_path = self._get_benchmark_path(benchmark, entry_point,
                                                  force_dir=force_dir)
        args = [self.iterations_runner,
                benchmark_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k, stack_lim_k,
                              sync_disks=sync_disks)

    def check_benchmark_files(self, benchmark, entry_point):
        benchmark_path = self._get_benchmark_path(benchmark, entry_point)
        if not os.path.exists(benchmark_path):
            fatal("Benchmark object non-existent: %s" % benchmark_path)


class GenericScriptingVMDef(BaseVMDef):
    def __init__(self, vm_path, iterations_runner, entry_point=None,
                 subdir=None, env=None, instrument=False):
        self.vm_path = vm_path
        self.extra_vm_args = []
        fp_iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)
        BaseVMDef.__init__(self, fp_iterations_runner, env=env,
                           instrument=instrument)

    def _generic_scripting_run_exec(self, entry_point, benchmark, iterations,
                                    param, heap_lim_k, stack_lim_k,
                                    force_dir=None, sync_disks=True):
        script_path = self._get_benchmark_path(benchmark, entry_point,
                                               force_dir=force_dir)
        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, script_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k, stack_lim_k,
                              sync_disks=sync_disks)

    def sanity_checks(self):
        BaseVMDef.sanity_checks(self)

        if not os.path.exists(self.vm_path):
            fatal("VM path non-existent: %s" % self.vm_path)

    def check_benchmark_files(self, benchmark, entry_point):
        script_path = self._get_benchmark_path(benchmark, entry_point)
        if not os.path.exists(script_path):
            fatal("Benchmark file non-existent: %s" % script_path)

class JavaVMDef(BaseVMDef):
    def __init__(self, vm_path, env=None):
        self.vm_path = vm_path
        self.extra_vm_args = []
        BaseVMDef.__init__(self, "IterationsRunner", env=env)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, entry_point, benchmark, iterations,
                 param, heap_lim_k, stack_lim_k, force_dir=None, sync_disks=True):
        """Running Java experiments is different due to the way that the JVM
        doesn't simply accept the path to a program to run. We have to set
        the CLASSPATH and then provide a class name instead"""

        bench_dir = os.path.dirname(self._get_benchmark_path(benchmark,
                                             entry_point, force_dir=force_dir))

        # deal with CLASSPATH
        # This has to be added here as it is benchmark specific
        bench_env_changes = [
            EnvChangeAppend("CLASSPATH", ITERATIONS_RUNNER_DIR),
            EnvChangeAppend("CLASSPATH", bench_dir),
        ]

        args = [self.vm_path] + self.extra_vm_args
        args += [self.iterations_runner,entry_point.target,
                 str(iterations), str(param)]

        return self._run_exec(args, heap_lim_k, stack_lim_k,
                              bench_env_changes=bench_env_changes,
                              sync_disks=sync_disks)

    def sanity_checks(self):
        BaseVMDef.sanity_checks(self)

        if not os.path.exists(self.vm_path):
            fatal("VM path non-existent: %s" % self.vm_path)

    def _get_classfile_path(self, benchmark, entry_point):
        return os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir,
                            entry_point.target + ".class")

    def check_benchmark_files(self, benchmark, entry_point):
        classfile_path = self._get_classfile_path(benchmark, entry_point)
        if not os.path.exists(classfile_path):
            fatal("Benchmark file non-existent: %s" % classfile_path)


def find_internal_jvmci_java_bin(base_dir):
    """
    The jvmci internal jdk8 seems to move around depending upon
    the JVM with which it was built.

    E.g. the java binary could be:
    jvmci/jdk1.8.0-internal/product/bin/java

    or it could be:
    jvmci/jdk1.8.0_66-internal/product/bin/java

    This is a helper function to try and find the 'java' binary
    inside this "moving" directory.

    arguments:
    base_dir -- base jvmci directory"""

    try:
        matches = fnmatch.filter(os.listdir(base_dir), 'jdk1.8.0*internal*')
    except OSError as e:
        # we didn't find an internal JDK
        fatal("couldn't find the JVMCI internal JDK")

    if len(matches) == 1:
        return os.path.join(base_dir, matches[0], "product", "bin", "java")
    elif len(matches) > 1:
        raise Exception("Found more than one jvmci internal jdk in %s" % base_dir)
    else:
        raise Exception("couldn't locate jvmci internal jdk in %s" % base_dir)


class GraalVMDef(JavaVMDef):
    def __init__(self, vm_path, java_home=None, env=None):
        JavaVMDef.__init__(self, vm_path, env=env)
        if java_home is not None:
            self.add_env_change(EnvChangeSet("JAVA_HOME", java_home))

        self.extra_vm_args.append("-jvmci")

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, entry_point, benchmark, iterations, param,
                 heap_lim_k, stack_lim_k, force_dir=None, sync_disks=True):
        return JavaVMDef.run_exec(self, entry_point, benchmark,
                                  iterations, param, heap_lim_k,
                                  stack_lim_k, force_dir=force_dir,
                                  sync_disks=sync_disks)

    def _check_jvmci_server_enabled(self):
        """Runs fake benchmark crashing if the Graal JVMCI JIT is disabled"""

        ep = EntryPoint("JavaCheckJVMCIServerEnabled", subdir=VM_SANITY_CHECKS_DIR)
        spawn_sanity_check(self.platform, ep, self, "JavaCheckJVMCIServerEnabled")

    def sanity_checks(self):
        JavaVMDef.sanity_checks(self)

        if not self.vm_path.endswith("java"):
            fatal("Graal vm_path should be a path to a jvmci enabled java binary")

        self._check_jvmci_server_enabled()

class PythonVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None, instrument=False):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.py",
                                       env=env, instrument=instrument)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, entry_point, benchmark, iterations,
                 param, heap_lim_k, stack_lim_k, force_dir=None, sync_disks=True):
        # heap_lim_k unused.
        # Python reads the rlimit structure to decide its heap limit.
        return self._generic_scripting_run_exec(entry_point, benchmark,
                                                iterations, param, heap_lim_k,
                                                stack_lim_k, force_dir=force_dir,
                                                sync_disks=sync_disks)


class PyPyVMEvent(object):
    """Represents an event of interest inside PyPy"""

    def __init__(self, event_type, start_time, parent):
        self.start_time = start_time
        self.event_type = event_type
        self.stop_time = None  # later
        self.children = []
        self.parent = parent
        if parent is not None:
            parent.children.append(self)

    def get_duration(self):
        """Get the time this event consumed, but not including the time
        spent in child events"""

        assert self.start_time is not None and \
            self.stop_time is not None

        total_time = self.stop_time - self.start_time
        child_time = sum(
            [child.get_duration() for child in self.children])

        assert total_time >= child_time
        return total_time - child_time

    def __repr__(self):
        """For debugging"""

        return "%s(start=%s, stop=%s, children=%s)" % \
            (self.event_type, self.start_time,
             self.stop_time, len(self.children))


class PyPyVMDef(PythonVMDef):
    # Describes PyPy's stderr instrumentation.
    # event-prefix -> counter-this-contributes-to
    #
    # Any JIT-related event in one counter, all GC-related in another.
    # Any other event is not counted.
    INSTRUMENTATION = {
        "jit-": "compilation_time",
        "gc-": "gc_time",
    }

    INST_START_EVENT_REGEX = re.compile("\[([0-9a-f]+)\] \{(.+)$")
    INST_STOP_EVENT_REGEX = re.compile("\[([0-9a-f]+)\] (.+)\}$")

    def __init__(self, vm_path, env=None, instrument=False):
        """When instrument=True, record GC and compilation events"""

        if instrument:
            if env is None:
                env = {}
            # Causes PyPy to emit VM events on stderr
            EnvChangeSet("PYPYLOG", "-").apply(env)

        PythonVMDef.__init__(self, vm_path, env=env, instrument=instrument)

        # XXX: On OpenBSD the PyPy build fails to encode the rpath to libpypy-c.so
        # into the VM executable, so we have to force it ourselves.
        #
        # For fairness, we apply the environment change to all platforms.
        #
        # Ideally fix in PyPy.
        # The user's environment (if any) comes first however
        lib_dir = os.path.dirname(vm_path)
        self.add_env_change(EnvChangeAppend("LD_LIBRARY_PATH", lib_dir))

    def parse_instrumentation_stderr_file(self, file_handle):
        """For PyPy we look in the stderr file for the start and end timestamps
        of some VM events that we are interested in. These timestamps are not
        in wall-clock time.
        """

        # Events are not necessarily sequential.
        #
        # GC can happen inside tracing, so we have to be a bit clever about how
        # we separate GC time from tracing.
        #
        # We treat the event stream like a tree. We walk this tree, keeping
        # track of the nesting, and when computing the time for each event, we
        # exclude each event's children. The children have their times computed
        # separately.

        # This stores the counters for all in-process iterations
        data = {
            "gc_time": [],
            "compilation_time": [],
        }

        # This stores the counters for the current in-process iteration
        data_this_iter = {
            "gc_time": 0,
            "compilation_time": 0
        }

        iter_num = 0
        current_event = None

        for line in file_handle:
            if line.startswith(INSTRUMENTATION_END_PROC_ITER_PREFIX):
                # first some sanity checking
                elems = line.split(":")
                assert(len(elems) == 2 and int(elems[1]) == iter_num)
                iter_num += 1
                assert current_event is None

                # store this iteration's data and prepare for the next
                for event in data_this_iter.iterkeys():
                    data[event].append(data_this_iter[event])
                    data_this_iter[event] = 0  # reset
                continue

            # Is it the start of an event?
            start_match = re.match(PyPyVMDef.INST_START_EVENT_REGEX, line)
            if start_match:
                start_time = int(start_match.groups()[0], 16)
                event_type = start_match.groups()[1]

                new_event = PyPyVMEvent(event_type, start_time, current_event)
                current_event = new_event
                continue

            # Is it the end of an event?
            stop_match = re.match(PyPyVMDef.INST_STOP_EVENT_REGEX, line)
            if stop_match:
                event_type = stop_match.groups()[1]
                current_event.stop_time = int(stop_match.groups()[0], 16)

                # check event is correctly nested
                assert event_type == current_event.event_type

                # Find which counter this event contributes to (if any)
                for prefix, counter_name in \
                        PyPyVMDef.INSTRUMENTATION.iteritems():
                    if event_type.startswith(prefix):
                        break  # found one
                else:
                    counter_name = None

                if counter_name is not None:
                    data_this_iter[counter_name] += current_event.get_duration()

                current_event = current_event.parent
                continue

        # All events should be done and dusted
        assert current_event is None

        return data


class LuaVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.lua",
                                       env=env)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        return self._generic_scripting_run_exec(interpreter, benchmark,
                                                iterations, param, heap_lim_k,
                                                stack_lim_k,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)

class PHPVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.php",
                                       env=env)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        return self._generic_scripting_run_exec(interpreter, benchmark,
                                                iterations, param, heap_lim_k,
                                                stack_lim_k,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)

class RubyVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.rb",
                                       env=env)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

class JRubyVMDef(RubyVMDef):
    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        return self._generic_scripting_run_exec(interpreter, benchmark,
                                                iterations, param, heap_lim_k,
                                                stack_lim_k,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)

class JRubyTruffleVMDef(JRubyVMDef):
    def __init__(self, vm_path, java_path, env=None):
        JRubyVMDef.__init__(self, vm_path, env=env)
        self.add_env_change(EnvChangeAppend("JAVACMD", java_path))

        self.extra_vm_args += ['-X+T', '-J-server']

    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        return self._generic_scripting_run_exec(
            interpreter, benchmark, iterations, param, heap_lim_k,
            stack_lim_k, force_dir=force_dir, sync_disks=sync_disks)

    def _check_truffle_enabled(self):
        """Runs fake benchmark crashing if the Truffle is disabled in JRuby"""

        debug("Running jruby_check_truffle_enabled sanity check")
        ep = EntryPoint("jruby_check_graal_enabled.rb")
        spawn_sanity_check(self.platform, ep, self,
                           "jruby_check_graal_enabled.rb", force_dir=VM_SANITY_CHECKS_DIR)

    def sanity_checks(self):
        JRubyVMDef.sanity_checks(self)
        self._check_truffle_enabled()

class JavascriptVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js", env=env)

    def parse_instrumentation_stderr_file(self, file_handle):
        pass


class V8VMDef(JavascriptVMDef):
    def parse_instrumentation_stderr_file(self, file_handle):
        pass

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k,
                 stack_lim_k, force_dir=None, sync_disks=True):
        # Duplicates generic implementation. Need to pass args differently.

        script_path = self._get_benchmark_path(benchmark, entry_point,
                                               force_dir=force_dir)

        # Note the double minus in the arguments.
        # V8 requires you to indicate the end of VM arguments and the start of
        # user program arguments with the '--' separator. This precludes the
        # use of run_exec() from the superclass, hence the existence of this
        # method.
        args = [self.vm_path] + self.extra_vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        return self._run_exec(args, heap_lim_k, stack_lim_k,
                              sync_disks=sync_disks)
