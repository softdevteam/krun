import subprocess
import os
import select
import fnmatch
import json
from abc import ABCMeta, abstractmethod

from logging import info, debug
from krun import EntryPoint
from krun.util import fatal
from krun.env import EnvChangeAppend, EnvChangeSet, EnvChange

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = os.path.abspath(os.path.join(os.getcwd(), "benchmarks"))
VM_SANITY_CHECKS_DIR = os.path.join(DIR, "..", "vm_sanity_checks")
SANITY_CHECK_HEAP_KB = 1024 * 1024  # 1GB

# Pipe buffer sizes vary. I've seen reports on the Internet ranging from a
# page size (Linux pre-2.6.11) to 64K (Linux in 2015). Ideally we would
# query the pipe for its capacity using F_GETPIPE_SZ, but this is a) not
# portable between UNIXs even, and b) not exposed by Python's fcntl(). For
# now, we use a "reasonable" buffer size. If it is larger than the pipe
# capacity, then no harm done; if it is smaller, then we may do more reads
# than are strictly necessary. In either case we are safe and correct.
PIPE_BUF_SZ = 1024 * 16

SELECT_TIMEOUT = 1.0


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

    def __init__(self, iterations_runner):
        self.iterations_runner = iterations_runner

        # List of EnvChange instances to apply prior to each experiment.
        # These should be benchmark agnostic. Look elsewhere for
        # environment changes specific to a benchmark.
        self.common_env_changes = []

        # tempting as it is to add a self.vm_path, we don't. If we were to add
        # natively compiled languages, then there is no "VM" to speak of.

        self.platform = None  # Set later

        # Do not execute the benchmark program
        # (useful for testing configurations.).
        self.dry_run = False

    def _get_benchmark_path(self, benchmark, entry_point, sanity_check=False):
        if not sanity_check:
            return os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir,
                                entry_point.target)
        else:
            return os.path.join(VM_SANITY_CHECKS_DIR, entry_point.target)

    def set_platform(self, platform):
        self.platform = platform

    def add_env_change(self, change):
        self.common_env_changes.append(change)

    @abstractmethod
    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k,
                 sanity_check=False):
        pass

    def _run_exec(self, args, heap_lim_k, bench_env_changes=None):
        """ Deals with actually shelling out """

        if bench_env_changes is None:
            bench_env_changes = []

        # Environment *after* user change.
        # Starts empty, but user change command (e.g. sudo/doas) may introduce some.
        new_user_env = {}

        # Apply vm specific environment changes
        EnvChange.apply_all(self.common_env_changes, new_user_env)

        # Apply benchmark specific environment changes
        EnvChange.apply_all(bench_env_changes, new_user_env)

        # This is kind of awkward. We don't have the heap limit at
        # VMDef construction time, so we have to substitute it in later.
        actual_args = []
        for a in args:
            if callable(a):
                a = a(heap_lim_k)
            actual_args.append(a)

        # Apply platform specific argument transformations.
        actual_args = self.platform.bench_cmdline_adjust(
            actual_args, new_user_env)

        debug("cmdline='%s'" % " ".join(actual_args))

        if self.dry_run:
            info("Dry run. Skipping.")
            return ("", "", 0)

        # We pass the empty environment dict here.
        # This is the *outer* environment that the current user will invoke the
        # command with. Command line arguments will have been appended *inside*
        # to adjust the new user's environment once the user switch has
        # occurred.
        p = subprocess.Popen(
            actual_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={})

        return self._run_exec_capture(p)

    def _run_exec_capture(self, child_pipe):
        """Allows the subprocess (whose pipes we have handles on) to run
        to completion. We print stderr as it arrives.

        Returns a triple: stderr, stdout and the returncode."""

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
                    stderr_data.append(d)
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

    def run_vm_sanity_check(self, entry_point):
        """Runs a VM specific sanity check (fake benchmark)."""

        # Use the same mechanism as the real benchmarks would use.
        iterations, param = 1, 666
        stdout, stderr, rc = self.run_exec(
            entry_point, None, iterations, param, SANITY_CHECK_HEAP_KB,
            sanity_check=True)

        err = rc != 0
        try:
            ls = json.loads(stdout)
        except ValueError:
            err = True

        if not err and not isinstance(ls, list):
            err = True

        if err:
            fatal("VM sanity check failed '%s'\n"
                  "return code: %s\nstdout:%s\nstderr: %s" %
                  (entry_point.target, rc, stdout, stderr))


class NativeCodeVMDef(BaseVMDef):
    """Not really a "VM definition" at all. Runs native code."""

    def __init__(self):
        iter_runner = os.path.join(ITERATIONS_RUNNER_DIR,
                                   "iterations_runner_c")
        BaseVMDef.__init__(self, iter_runner)

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k,
                 sanity_check=False):
        benchmark_path = self._get_benchmark_path(benchmark, entry_point,
                                                  sanity_check=sanity_check)
        args = [self.iterations_runner,
                benchmark_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k)

    def check_benchmark_files(self, benchmark, entry_point):
        benchmark_path = self._get_benchmark_path(benchmark, entry_point)
        if not os.path.exists(benchmark_path):
            fatal("Benchmark object non-existent: %s" % benchmark_path)


class GenericScriptingVMDef(BaseVMDef):
    def __init__(self, vm_path, iterations_runner, entry_point=None, subdir=None):
        self.vm_path = vm_path
        self.extra_vm_args = []
        fp_iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)
        BaseVMDef.__init__(self, fp_iterations_runner)

    def _generic_scripting_run_exec(self, entry_point, benchmark, iterations,
                                    param, heap_lim_k, sanity_check=False):
        script_path = self._get_benchmark_path(benchmark, entry_point,
                                               sanity_check=sanity_check)
        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, script_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k)

    def sanity_checks(self):
        BaseVMDef.sanity_checks(self)

        if not os.path.exists(self.vm_path):
            fatal("VM path non-existent: %s" % self.vm_path)

    def check_benchmark_files(self, benchmark, entry_point):
        script_path = self._get_benchmark_path(benchmark, entry_point)
        if not os.path.exists(script_path):
            fatal("Benchmark file non-existent: %s" % script_path)

class JavaVMDef(BaseVMDef):
    def __init__(self, vm_path):
        self.vm_path = vm_path
        self.extra_vm_args = [lambda heap_lim_k: "-Xmx%sK" % heap_lim_k]
        BaseVMDef.__init__(self, "IterationsRunner")

    def run_exec(self, entry_point, benchmark, iterations,
                 param, heap_lim_k, sanity_check=False):
        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, entry_point.target, str(iterations), str(param)]

        if not sanity_check:
            bench_dir = os.path.abspath(
                os.path.join(os.getcwd(), BENCHMARKS_DIR, benchmark, entry_point.subdir))
        else:
            bench_dir = VM_SANITY_CHECKS_DIR

        # deal with CLASSPATH
        # This has to be added here as it is benchmark specific
        bench_env_changes = [
            EnvChangeAppend("CLASSPATH", ITERATIONS_RUNNER_DIR),
            EnvChangeAppend("CLASSPATH", bench_dir),
        ]

        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, entry_point.target, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k,
                              bench_env_changes=bench_env_changes)

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

    matches = fnmatch.filter(os.listdir(base_dir), 'jdk1.8.0*internal*')

    if len(matches) == 1:
        return os.path.join(base_dir, matches[0], "product", "bin", "java")
    elif len(matches) > 1:
        raise Exception("Found more than one jvmci internal jdk in %s" % base_dir)
    else:
        raise Exception("couldn't locate jvmci internal jdk in %s" % base_dir)


class GraalVMDef(JavaVMDef):
    def __init__(self, vm_path, java_home=None):
        JavaVMDef.__init__(self, vm_path)
        if java_home is not None:
            self.add_env_change(EnvChangeSet("JAVA_HOME", java_home))

        self.extra_vm_args.append("-jvmci")

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k, sanity_check=False):
        return JavaVMDef.run_exec(self, entry_point, benchmark,
                                  iterations, param, heap_lim_k, sanity_check=sanity_check)

    def _check_jvmci_server_enabled(self):
        """Runs fake benchmark crashing if the Graal JVMCI JIT is disabled"""

        info("Running JavaCheckJVMCIServerEnabled sanity check")
        ep = EntryPoint("JavaCheckJVMCIServerEnabled")
        self.run_vm_sanity_check(ep)

    def sanity_checks(self):
        JavaVMDef.sanity_checks(self)

        if not self.vm_path.endswith("java"):
            fatal("Graal vm_path should be a path to a jvmci enabled java binary")

        self._check_jvmci_server_enabled()

class PythonVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.py")

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        # heap_lim_k unused.
        # Python reads the rlimit structure to decide its heap limit.
        return self._generic_scripting_run_exec(entry_point, benchmark,
                                                iterations, param, heap_lim_k)

class LuaVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.lua")

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        # I was unable to find any special switches to limit lua's heap size.
        # Looking at implementationsi:
        #  * luajit uses anonymous mmap() to allocate memory, fiddling
        #    with rlimits prior.
        #  * Stock lua doesn't seem to do anything special. Just realloc().
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class PHPVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.php")
        self.extra_vm_args += ["-d", lambda heap_lim_k: "memory_limit=%sK" % heap_lim_k]

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class RubyVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.rb")

class JRubyVMDef(RubyVMDef):
    def __init__(self, vm_path):
        RubyVMDef.__init__(self, vm_path)
        self.extra_vm_args += [lambda heap_lim_k: "-J-Xmx%sK" % heap_lim_k]

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class JRubyTruffleVMDef(JRubyVMDef):
    def __init__(self, vm_path, java_path):
        JRubyVMDef.__init__(self, vm_path)
        self.add_env_change(EnvChangeAppend("JAVACMD", java_path))

        self.extra_vm_args += ['-X+T', '-J-server']

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k,
                 sanity_check=False):
        return self._generic_scripting_run_exec(
            interpreter, benchmark, iterations, param, heap_lim_k,
            sanity_check=sanity_check)

    def _check_truffle_enabled(self):
        """Runs fake benchmark crashing if the Truffle is disabled in JRuby"""

        info("Running jruby_check_truffle_enabled sanity check")
        ep = EntryPoint("jruby_check_graal_enabled.rb")
        self.run_vm_sanity_check(ep)

    def sanity_checks(self):
        JRubyVMDef.sanity_checks(self)
        self._check_truffle_enabled()

class JavascriptVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js")


class V8VMDef(JavascriptVMDef):
    def __init__(self, vm_path):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js")

        # this is a best effort at limiting the heap space.
        # V8 has a "new" and "old" heap. I can't see a way to limit the total of the two.
        self.extra_vm_args += ["--max_old_space_size", lambda heap_lim_k: "%s" % int(heap_lim_k / 1024)] # as MB


    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        # Duplicates generic implementation. Need to pass args differently.

        script_path = os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir, entry_point.target)
        args = [self.vm_path] + self.extra_vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        return self._run_exec(args, heap_lim_k)
