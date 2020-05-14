import subprocess32
import os
import fnmatch
import re
import json
import getpass
import stat
import util
from tempfile import NamedTemporaryFile
import tempfile
from abc import ABCMeta, abstractmethod

from logging import debug, warn
from krun import EntryPoint
from krun.util import (fatal, spawn_sanity_check, VM_SANITY_CHECKS_DIR,
                       read_popen_output_carefully)
from krun.env import EnvChangeAppend, EnvChangeSet, EnvChange
from distutils.spawn import find_executable

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = os.path.abspath(os.path.join(os.getcwd(), "benchmarks"))
BENCHMARK_USER = "krun"
INST_STDERR_FILE = "/tmp/krun.stderr"

DASH = find_executable("dash")
if DASH is None:
    fatal("dash shell not found")


# !!!
# Don't mutate any lists passed down from the user's config file!
# !!!



class BaseVMDef(object):
    __metaclass__ = ABCMeta

    # Everyone read, only owner write
    WRAPPER_SCRIPT_MODE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH \
        | stat.S_IWUSR

    # Read/write for user and group
    ENVLOG_MODE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IWUSR | stat.S_IWGRP

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
    def run_exec(self, entry_point, iterations, param, heap_lim_k,
                 stack_lim_k, key, key_pexec_idx, force_dir=None, sync_disks=True):
        pass

    def make_wrapper_script(self, args, heap_lim_k, stack_lim_k):
        """Write the wrapper script.
        Separate for testing purposes.

        Returns a pair, the (unique) filename of the wrapper script, and the
        (unique) filename of where the (temporary) environment log will be
        written"""

        # Make a tempfile for the environment log
        fd, envlog_filename = tempfile.mkstemp(prefix="envlog-", suffix=".env")
        os.close(fd)  # we just need the name

        lines = [
            "#!%s" % DASH,
            "ENVLOG=`env`",  # store in memory to avoid IO prior to benchmark
            "ulimit -d %s || exit $?" % heap_lim_k,
            "ulimit -s %s || exit $?" % stack_lim_k,
            " ".join(args),
            # quotes around ENVLOG required to have one var per-line
            "echo \"${ENVLOG}\" > %s" % envlog_filename,
            "exit $?",
        ]
        with NamedTemporaryFile(prefix="krunwrapper-", suffix=".dash",
                                delete=False) as fh:
            wrapper_filename = fh.name
            debug("Writing out wrapper script to %s" % wrapper_filename)
            for line in lines:
                fh.write(line + "\n")
        debug("Wrapper script:\n%s" % ("\n".join(lines)))
        os.chmod(wrapper_filename, BaseVMDef.WRAPPER_SCRIPT_MODE)

        # Make the file R/W for both users.
        # We need root to transfer ownership to BENCHMARK_USER.
        os.chmod(envlog_filename, BaseVMDef.ENVLOG_MODE)
        if not self.platform.no_user_change:
            chown_args = self.platform.change_user_args("root") + \
                ["chown", BENCHMARK_USER, envlog_filename]
            util.run_shell_cmd(" ".join(chown_args))

        return wrapper_filename, envlog_filename

    def _run_exec(self, args, heap_lim_k, stack_lim_k, key, key_pexec_idx,
                  bench_env_changes=None, sync_disks=True):
        """ Deals with actually shelling out """

        if bench_env_changes is None:
            bench_env_changes = []

        # Environment *after* user change.
        # Starts minimal, but user change command (i.e. sudo) may introduce more.
        new_user_env = {"PATH": "/bin:/usr/bin"}

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

        # Tack on the instrumentation arguments, if required.
        if self.instrument:
            args.append(util.get_instr_json_dir(self.config))
            # we will redirect stderr to this handle
            stderr_file = open(INST_STDERR_FILE, "w")
            # Append flags only present in instrumentation mode.
            args.extend([key, str(key_pexec_idx)])

        else:
            stderr_file = subprocess32.PIPE

        if self.dry_run:
            warn("SIMULATED: Benchmark process execution (--dryrun)")
            return ("", "", 0, None, False)

        if not self.platform.no_user_change:
            self.platform.make_fresh_krun_user()
            # If we are in instrumentation mode, grant the Krun user write
            # access to the instrumentation directory.
            if self.instrument:
                util.set_instr_dir_perms(self.config, self.platform)

        wrapper_filename, envlog_filename = \
            self.make_wrapper_script(args, heap_lim_k, stack_lim_k)
        wrapper_args = self._wrapper_args(wrapper_filename)
        debug("Execute wrapper: %s" % (" ".join(wrapper_args)))

        # Do an OS-level sync. Forces pending writes on to the physical disk.
        # We do this in an attempt to prevent disk commits happening during
        # benchmarking.
        if sync_disks:
            self.platform.sync_disks()

        out, err, rc, timed_out = self._run_exec_popen(wrapper_args, stderr_file)

        if self.instrument:
            stderr_file.close()

        os.unlink(wrapper_filename)
        return out, err, rc, envlog_filename, timed_out

    # separate for testing
    def _wrapper_args(self, wrapper_filename):
        """Build arguments used to run the wrapper script"""

        wrapper_args = self.platform.change_user_args("root") + \
            self.platform.process_priority_args()

        if self.config.ENABLE_PINNING:
                wrapper_args += self.platform.pin_process_args()

        if self.platform.no_user_change:
            warn("Not changing user (--no-change-user)")
            # We still have to sudo back to the user who ran krun, as we raised
            # privs to root in order to nice the process etc.
            wrapper_args += self.platform.change_user_args(getpass.getuser())
        else:
            wrapper_args += self.platform.change_user_args(BENCHMARK_USER)

        wrapper_args += [DASH, wrapper_filename]

        return wrapper_args

    # separate for testing purposes
    def _run_exec_popen(self, args, stderr_file=subprocess32.PIPE):
        """popen to the wrapper script

        arguments:
          args: list of arguments to pass to popen().
          stderr_filename: if specified (as a string), write stderr to this filename.

        Returns a 3-tuple: stderr, stdout, returncode.
        """

        # We pass the empty environment dict here.
        # This is the *outer* environment that the current user will invoke the
        # command with. Command line arguments will have been appended *inside*
        # to adjust the new user's environment once the user switch has
        # occurred.
        child_pipe = subprocess32.Popen(args, stdout=subprocess32.PIPE,
                                      stderr=stderr_file, env={})
        return read_popen_output_carefully(child_pipe, platform=self.platform,
            timeout=self.config.EXECUTION_TIMEOUT)

    def sanity_checks(self):
        pass

    @abstractmethod
    def check_benchmark_files(self, benchmark, entry_point):
        pass

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def parse_instr_stderr_file(self, file_handle):
        """Parse instrumentation data. Override as necessary"""
        return {}

    def get_instr_data(self):
        with open(INST_STDERR_FILE, "r") as fh:
            return self.parse_instr_stderr_file(fh)


class ExternalSuiteVMDef(BaseVMDef):
    """Not really a "VM definition". This runs an arbitrary script which is
    expected to run one process execution and write the results to stdout. This
    is useful if you want to wrap an external benchmark suite, but note that
    you won't get any of the advanced Krun goodies like A/MPERF ratio checks or
    core-cycle counts."""

    def __init__(self, script_path, env=None):
        BaseVMDef.__init__(self, None, env=env, instrument=False)
        self.script_path = script_path

    def run_exec(self, _entry_point, iterations, param, heap_lim_k,
                 stack_lim_k, key, key_pexec_idx, force_dir=None, sync_disks=True):
        benchmark = key.split(":")[0]
        args = [self.script_path, benchmark, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k, stack_lim_k, key,
                              key_pexec_idx, sync_disks=sync_disks)

    def check_benchmark_files(self, _benchmark, _entry_point):
        if not os.path.exists(self.script_path):
            fatal("External script non-existent: %s" % self.script_path)


class NativeCodeVMDef(BaseVMDef):
    """Not really a "VM definition" at all. Runs native code."""

    def __init__(self, env=None):
        iter_runner = os.path.join(ITERATIONS_RUNNER_DIR,
                                   "iterations_runner_c")
        BaseVMDef.__init__(self, iter_runner, env=env)

    def run_exec(self, entry_point, iterations, param, heap_lim_k,
                 stack_lim_k, key, key_pexec_idx, force_dir=None,
                 sync_disks=True):
        benchmark = key.split(":")[0]
        benchmark_path = self._get_benchmark_path(benchmark, entry_point,
                                                  force_dir=force_dir)
        args = [self.iterations_runner,
                benchmark_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k, stack_lim_k, key,
                              key_pexec_idx, sync_disks=sync_disks)

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

    def _generic_scripting_run_exec(self, entry_point, iterations,
                                    param, heap_lim_k, stack_lim_k, key,
                                    key_pexec_idx, force_dir=None,
                                    sync_disks=True):
        benchmark = key.split(":")[0]
        script_path = self._get_benchmark_path(benchmark, entry_point,
                                               force_dir=force_dir)
        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, script_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k, stack_lim_k, key,
                              key_pexec_idx, sync_disks=sync_disks)

    def sanity_checks(self):
        BaseVMDef.sanity_checks(self)

        if not os.path.exists(self.vm_path):
            fatal("VM path non-existent: %s" % self.vm_path)

    def check_benchmark_files(self, benchmark, entry_point):
        script_path = self._get_benchmark_path(benchmark, entry_point)
        if not os.path.exists(script_path):
            fatal("Benchmark file non-existent: %s" % script_path)

class JavaVMDef(BaseVMDef):
    INSTR_MARKER = "@@@ JDK_EVENTS: "

    def __init__(self, vm_path, env=None, instrument=False):
        self.vm_path = vm_path
        self.extra_vm_args = []
        BaseVMDef.__init__(self, "IterationsRunner", env=env,
                           instrument=instrument)

    def run_exec(self, entry_point, iterations,
                 param, heap_lim_k, stack_lim_k, key, key_pexec_idx,
                 force_dir=None, sync_disks=True):
        """Running Java experiments is different due to the way that the JVM
        doesn't simply accept the path to a program to run. We have to set
        the CLASSPATH and then provide a class name instead"""

        benchmark = key.split(":")[0]
        bench_dir = os.path.dirname(self._get_benchmark_path(
            benchmark, entry_point, force_dir=force_dir))

        # deal with CLASSPATH
        # This has to be added here as it is benchmark specific
        bench_env_changes = [
            EnvChangeAppend("CLASSPATH", ITERATIONS_RUNNER_DIR),
            EnvChangeAppend("CLASSPATH", bench_dir),
        ]

        args = [self.vm_path] + self.extra_vm_args
        args += [self.iterations_runner, entry_point.target,
                 str(iterations), str(param)]

        return self._run_exec(args, heap_lim_k, stack_lim_k, key,
                              key_pexec_idx,
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

    def parse_instr_stderr_file(self, file_handle):
        """Read in compilation and GC event info from our strategically placed
        stderr lines.

        This function returns a dict with a single key "raw_vm_events", mapping
        to a list containing JVM instrumentation records (one per in-process
        iteration). See the comment in the iterations runner for the format of
        the records."""

        iter_num = 0
        iter_data = []
        prefix_len = len(JavaVMDef.INSTR_MARKER)
        for line in file_handle:
            if not line.startswith(JavaVMDef.INSTR_MARKER):
                continue
            line = line[prefix_len:]
            data = json.loads(line)
            assert data[0] == iter_num
            iter_data.append(data)
            iter_num += 1

        return {"raw_vm_events": iter_data}


def find_internal_jvmci_java_home(base_dir):
    """
    The jvmci jdk8 is named according to the JVM that was used to build it.

    Point this function at the 'jvmci' dir and it will return the JAVA_HOME for
    the jvmci JDK.

    arguments:
    base_dir -- base jvmci directory"""

    try:
        matches = fnmatch.filter(os.listdir(base_dir), 'jdk1.8*')
    except OSError:
        # we didn't find an internal JDK
        fatal("couldn't find the JVMCI internal JDK")

    if len(matches) == 1:
        return os.path.join(base_dir, matches[0], "product")
    elif len(matches) > 1:
        raise Exception("Found more than one jvmci internal jdk in %s" % base_dir)
    else:
        raise Exception("couldn't locate jvmci internal jdk in %s" % base_dir)


def find_internal_jvmci_java_bin(base_dir):
    return os.path.join(find_internal_jvmci_java_home(base_dir), "bin", "java")


class GraalVMDef(JavaVMDef):
    def __init__(self, graal_dir, mx_path, java_home=None, env=None):
        JavaVMDef.__init__(self, mx_path, env=env)

        # This is for the JDK8 targetted version of graal.  Once JDK9 is
        # available it will include Graal and running the VM should be much
        # simpler. Hopefully just invoking 'java' with some flag.
        self.extra_vm_args += ['-p', graal_dir, 'vm', '-XX:+UseJVMCICompiler']

        if java_home is not None:
            self.add_env_change(EnvChangeSet("JAVA_HOME", java_home))

    def run_exec(self, entry_point, iterations, param, heap_lim_k, stack_lim_k,
                 key, key_pexec_idx, force_dir=None, sync_disks=True):
        return JavaVMDef.run_exec(self, entry_point, iterations, param,
                                  heap_lim_k, stack_lim_k, key, key_pexec_idx,
                                  force_dir=force_dir, sync_disks=sync_disks)

    def _check_jvmci_server_enabled(self):
        """Runs fake benchmark crashing if the Graal JVMCI JIT is disabled"""

        ep = EntryPoint("JavaCheckJVMCIServerEnabled", subdir=VM_SANITY_CHECKS_DIR)
        spawn_sanity_check(self.platform, ep, self, "JavaCheckJVMCIServerEnabled")

    def sanity_checks(self):
        JavaVMDef.sanity_checks(self)

        if not self.vm_path != "mx":
            fatal("Graal's vm_path should be a path to an 'mx' script")

        self._check_jvmci_server_enabled()

class PythonVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None, instrument=False):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.py",
                                       env=env, instrument=instrument)

    def run_exec(self, entry_point, iterations, param, heap_lim_k, stack_lim_k,
                 key, key_pexec_idx, force_dir=None, sync_disks=True):
        # heap_lim_k unused.
        # Python reads the rlimit structure to decide its heap limit.
        return self._generic_scripting_run_exec(entry_point, iterations, param,
                                                heap_lim_k, stack_lim_k, key,
                                                key_pexec_idx,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)


class PyPyVMDef(PythonVMDef):
    INST_START_EVENT_REGEX = re.compile("\[([0-9a-f]+)\] \{(.+)$")
    INST_STOP_EVENT_REGEX = re.compile("\[([0-9a-f]+)\] (.+)\}$")
    INST_END_PROC_ITER_PREFIX = "@@@ END_IN_PROC_ITER:"
    INST_JIT_TIME_PREFIX = "@@@ JIT_TIME:"

    def __init__(self, vm_path, env=None, instrument=False):
        """When instrument=True, record GC and compilation events"""

        if instrument:
            if env is None:
                env = {}
            # Causes PyPy to emit VM events on stderr
            EnvChangeSet("PYPYLOG", "gc:-").apply(env)

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

    def parse_instr_stderr_file(self, file_handle):
        """PyPy instrumentation data collected from the PYPYLOG.

        We record when GC events begin and end. Events may be nested.  We
        consume the event stream, building a tree which will be saved away
        later.

        The tree itself is a (compact) JSON-compatible representation. Each
        in-process iteration has one such tree, whose nodes represent VM
        events. The nodes are lists of the form:
          [event_type, start_time, stop_time, children]

        Time-stamps in the tree nodes are not in wall-clock time. Consider the
        units arbitrary. This means that comparisons to wall clock times are
        invalid, however you can report the times relative to each other, e.g.:

        "In iteration X the VM spent twice as long in compilation-related
        events than iteration Y. This is reflected by a larger spike in the
        iteration time for X."

        Each tree always starts with a dummy root node, whose event type is
        "root" and whose start and stop times are None.

        This function returns a dict with a single key "raw_vm_events", mapping
        to a list of root nodes, one per in-process iteration.

        Note that this parser assumes that events do not cross event
        boundaries, and cannot be used with tracing events therefore.
        """

        def root_node():
            return ["root", None, None, []]

        jit_times = []
        trees = []
        parent_stack = []
        current_node = root_node()
        iter_num = 0
        for line in file_handle:
            if line.startswith(PyPyVMDef.INST_END_PROC_ITER_PREFIX):
                # first some sanity checking
                elems = line.split(":")
                assert(len(elems) == 2 and int(elems[1]) == iter_num)
                iter_num += 1

                # Nesting level at the end of an iteration should be 0.
                assert current_node[0] == "root" and len(parent_stack) == 0

                trees.append(current_node)
                current_node = root_node()  # new tree for next iteration
                continue
            if line.startswith(PyPyVMDef.INST_JIT_TIME_PREFIX):
                jit_times.append(float(line[len(PyPyVMDef.INST_JIT_TIME_PREFIX):]))
                continue

            # Is it the start of an event?
            start_match = re.match(PyPyVMDef.INST_START_EVENT_REGEX, line)
            if start_match:
                start_time = int(start_match.groups()[0], 16)
                event_type = start_match.groups()[1]

                # The new node stores a reference to its parent.
                # The stop time is not yet known, and is thus None.
                new_node = [event_type, start_time, None, []]
                current_node[3].append(new_node)  # register as child
                parent_stack.append(current_node)
                current_node = new_node
                continue

            # Is it the end of an event?
            stop_match = re.match(PyPyVMDef.INST_STOP_EVENT_REGEX, line)
            if stop_match:
                # Check the events are properly nested
                event_type = stop_match.groups()[1]
                assert event_type == current_node[0]

                # Now we know the stop time, so fill it in
                stop_time = int(stop_match.groups()[0], 16)
                current_node[2] = stop_time

                # Check the event times make sense
                assert current_node[1] < current_node[2]

                # Restore the parent as the current event
                current_node = parent_stack.pop()
                continue

        # When we are done, we should be at nesting level 0 with a root node
        assert current_node[0] == "root" and len(parent_stack) == 0

        return {"raw_vm_events": trees, "jit_times": jit_times}


class LuaVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.lua",
                                       env=env)

    def run_exec(self, interpreter, iterations, param, heap_lim_k,
                 stack_lim_k, key, key_pexec_idx, force_dir=None,
                 sync_disks=True):
        return self._generic_scripting_run_exec(interpreter, iterations, param,
                                                heap_lim_k, stack_lim_k, key,
                                                key_pexec_idx,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)

class PHPVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.php",
                                       env=env)

    def run_exec(self, interpreter, iterations, param, heap_lim_k,
                 stack_lim_k, key, key_pexec_idx, force_dir=None,
                 sync_disks=True):
        return self._generic_scripting_run_exec(interpreter, iterations, param,
                                                heap_lim_k, stack_lim_k, key,
                                                key_pexec_idx,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)

class RubyVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.rb",
                                       env=env)

class TruffleRubyVMDef(RubyVMDef):
    def __init__(self, truffleruby_dir=None, graal_home=None, mx_dir=None,
                 jvmci_home=None, env=None):
        """
        Args:
            truffleruby_dir: path to a (built) truffleruby src dir
            graal_home: path to the built graal-core directory
            mx_dir: path to mx directory

        Note that this is for the open-source graal-core powered TruffleRuby,
        not for the proprietary graalvm binaries found on Oracle Technology
        Network.
        """

        jtrb_path = os.path.join(truffleruby_dir, 'tool', 'jt.rb')
        mx_bin_dir = os.path.join(mx_dir, "bin")

        RubyVMDef.__init__(self, jtrb_path, env=env)
        self.add_env_change(EnvChangeAppend("GRAAL_HOME", graal_home))
        self.add_env_change(EnvChangeAppend("PATH", mx_dir))
        self.extra_vm_args += ['run', '--graal']

        if jvmci_home is not None:
            self.add_env_change(EnvChangeSet("JAVA_HOME", jvmci_home))

    def run_exec(self, interpreter, iterations, param, heap_lim_k, stack_lim_k,
                 key, key_pexec_idx, force_dir=None, sync_disks=True):
        return self._generic_scripting_run_exec(interpreter, iterations, param,
                                                heap_lim_k, stack_lim_k, key,
                                                key_pexec_idx,
                                                force_dir=force_dir,
                                                sync_disks=sync_disks)

    def _check_truffle_enabled(self):
        """Runs fake benchmark crashing if the Truffle is disabled in
        TruffleRuby"""

        debug("Running truffleruby_check_truffle_enabled sanity check")
        ep = EntryPoint("truffleruby_check_graal_enabled.rb")
        spawn_sanity_check(self.platform, ep, self,
                           "truffleruby_check_graal_enabled.rb",
                           force_dir=VM_SANITY_CHECKS_DIR)

    def sanity_checks(self):
        RubyVMDef.sanity_checks(self)
        self._check_truffle_enabled()

class JavascriptVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js", env=env)


class V8VMDef(JavascriptVMDef):
    def run_exec(self, entry_point, iterations, param, heap_lim_k,
                 stack_lim_k, key, key_pexec_idx, force_dir=None,
                 sync_disks=True):
        # Duplicates generic implementation. Need to pass args differently.

        benchmark = key.split(":")[0]
        script_path = self._get_benchmark_path(benchmark, entry_point,
                                               force_dir=force_dir)

        # Note the double minus in the arguments.
        # V8 requires you to indicate the end of VM arguments and the start of
        # user program arguments with the '--' separator. This precludes the
        # use of run_exec() from the superclass, hence the existence of this
        # method.
        args = [self.vm_path] + self.extra_vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        return self._run_exec(args, heap_lim_k, stack_lim_k, key,
                              key_pexec_idx, sync_disks=sync_disks)
