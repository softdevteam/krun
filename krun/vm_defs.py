import subprocess
import os

from logging import info, debug
from krun import EntryPoint
from krun.util import fatal

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = os.path.abspath(os.path.join(os.getcwd(), "benchmarks"))
VM_SANITY_CHECKS_DIR = os.path.join(DIR, "..", "vm_sanity_checks")
SANITY_CHECK_HEAP_KB = 1024 * 1024  # 1GB


# !!!
# Don't mutate any lists passed down from the user's config file!
# !!!

BASE_ENV = os.environ.copy()
BASE_ENV.update({"LD_LIBRARY_PATH": os.path.join(DIR, "..", "libkruntime")})


class EnvChange(object):
    def __init__(self, var, val):
        self.var, self.val = var, val


    @staticmethod
    def apply_all(changes, env):
        """Apply a collection of changes"""
        for change in changes:
            change.apply(env)

    def apply(self, env):
        raise NotImplementedError("abstract")


class EnvChangeSet(EnvChange):
    def apply(self, env):
        cur_val = env.get(self.var, None)
        if cur_val is not None:
            fatal("Environment %s is already defined" % self.var)
        else:
            env[self.var] = self.val


class EnvChangeAppend(EnvChange):
    def apply(self, env):
        cur_val = env.get(self.var, None)
        if cur_val is None:
            env[self.var] = self.val
        else:
            env[self.var] = "%s%s%s" % (cur_val, os.pathsep, self.val)


class BaseVMDef(object):
    def __init__(self, iterations_runner):
        self.iterations_runner = iterations_runner

        # List of EnvChange instances to apply prior to each experiment.
        # These should be benchmark agnostic. Look elsewhere for
        # environment changes specific to a benchmark.
        self.common_env_changes = []

        # tempting as it is to add a self.vm_path, we don't. If we were to add
        # natively compiled languages, then there is no "VM" to speak of.

        self.platform = None  # Set later

    def set_platform(self, platform):
        self.platform = platform

    def add_env_change(self, change):
        self.common_env_changes.append(change)

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        raise NotImplementedError("abstract")

    def _run_exec(self, args, heap_lim_k, bench_env_changes=None):
        """ Deals with actually shelling out """

        if bench_env_changes is None:
            bench_env_changes = []

        use_env = BASE_ENV.copy()
        # Apply vm specific environment changes
        EnvChange.apply_all(self.common_env_changes, use_env)

        # Apply benchmark specific environment changes
        EnvChange.apply_all(bench_env_changes, use_env)

        # This is kind of awkward. We don't have the heap limit at
        # VMDef construction time, so we have to substitute it in later.
        actual_args = []
        for a in args:
            if hasattr(a, "__call__"):  # i.e. a function
                a = a(heap_lim_k)
            actual_args.append(a)

        # Apply platform specific argument transformations.
        actual_args = self.platform.bench_cmdline_adjust(actual_args)

        debug("cmdline='%s'" % " ".join(actual_args))
        debug("env='%s'" % use_env)

        if os.environ.get("BENCH_DRYRUN") is not None:
            info("Dry run. Skipping.")
            return "[]"

        p = subprocess.Popen(
            actual_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=use_env)
        stdout, stderr = p.communicate()

        return stdout, stderr, p.returncode

    def sanity_checks(self):
        pass

    def check_benchmark_files(self, ep):
        raise NotImplementedError("abstract")

    def run_vm_sanity_check(self, entry_point):
        """Runs a VM specific sanity check (fake benchmark)."""

        # Use the same mechanism as the real benchmarks would use.
        iterations, param = 1, 666
        stdout, stderr, rc = self.run_exec(
            entry_point, None, iterations, param, SANITY_CHECK_HEAP_KB,
            sanity_check=True)

        err = rc != 0
        try:
            ls = eval(stdout)
        except:
            err = True

        if not err and not isinstance(ls, list):
            err = True

        if err:
            fatal("VM sanity check failed '%s'\n"
                  "return code: %s\nstdout:%s\nstderr: %s" %
                  (entry_point.target, rc, stdout, stderr))

class GenericScriptingVMDef(BaseVMDef):
    def __init__(self, vm_path, iterations_runner, entry_point=None, subdir=None):
        self.vm_path = vm_path
        self.extra_vm_args = []
        fp_iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)
        BaseVMDef.__init__(self, fp_iterations_runner)

    def _get_script_path(self, benchmark, entry_point, sanity_check=False):
        if not sanity_check:
            return os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir,
                                entry_point.target)
        else:
            return os.path.join(VM_SANITY_CHECKS_DIR, entry_point.target)

    def _generic_scripting_run_exec(self, entry_point, benchmark, iterations,
                                    param, heap_lim_k, sanity_check=False):
        script_path = self._get_script_path(benchmark, entry_point,
                                            sanity_check=sanity_check)
        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, script_path, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k)

    def sanity_checks(self):
        BaseVMDef.sanity_checks(self)

        if not os.path.exists(self.vm_path):
            fatal("VM path non-existent: %s" % self.vm_path)

    def check_benchmark_files(self, benchmark, entry_point):
        script_path = self._get_script_path(benchmark, entry_point)
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
