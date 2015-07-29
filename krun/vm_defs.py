import subprocess
import os

from logging import info, debug
from krun.util import fatal

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = "benchmarks"

# !!!
# Don't mutate any lists passed down from the user's config file!
# !!!

BASE_ENV = os.environ.copy()
BASE_ENV.update({"LD_LIBRARY_PATH": os.path.join(DIR, "..", "libkruntime")})

class BaseVMDef(object):

    def __init__(self, iterations_runner, extra_env=None):
        self.iterations_runner = iterations_runner
        if extra_env is None:
            extra_env = {}
        self.extra_env = extra_env
        # tempting as it is to add a self.vm_path, we don't. If we were to add
        # natively compiled languages, then there is no "VM" to speak of.

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        raise NotImplementedError("abstract")

    def _run_exec(self, args, heap_lim_k, bench_env=None):
        """ Deals with actually shelling out """

        use_env = BASE_ENV.copy()
        use_env.update(self.extra_env)  # VM specific env
        if bench_env:
            use_env.update(bench_env)   # bench specific env

        # This is kind of awkward. We don't have the heap limit at
        # VMDef construction time, so we have to substitute it in later.
        actual_args = []
        for a in args:
            if hasattr(a, "__call__"):  # i.e. a function
                a = a(heap_lim_k)
            actual_args.append(a)

        debug("cmdline='%s'" % " ".join(actual_args))
        debug("env='%s'" % use_env)

        if os.environ.get("BENCH_DRYRUN") is not None:
            info("Dry run. Skipping.")
            return "[]"

        stdout, stderr = subprocess.Popen(
            actual_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=use_env).communicate()
        return stdout, stderr

    def sanity_checks(self):
        pass

    def check_benchmark_files(self, ep):
        raise NotImplementedError("abstract")

class GenericScriptingVMDef(BaseVMDef):
    def __init__(self, vm_path, iterations_runner, entry_point=None, subdir=None, extra_env=None):
        self.vm_path = vm_path
        self.extra_vm_args = []
        fp_iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)
        BaseVMDef.__init__(self, fp_iterations_runner, extra_env=extra_env)

    def _get_script_path(self, benchmark, entry_point):
        return os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir,
                            entry_point.target)

    def _generic_scripting_run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        script_path = self._get_script_path(benchmark, entry_point)
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
    def __init__(self, vm_path, extra_env=None):
        self.vm_path = vm_path
        self.extra_vm_args = [lambda heap_lim_k: "-Xmx%sK" % heap_lim_k]
        BaseVMDef.__init__(self, "IterationsRunner", extra_env=extra_env)

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, entry_point.target, str(iterations), str(param)]
        bench_dir = os.path.abspath(os.path.join(os.getcwd(), BENCHMARKS_DIR, benchmark, entry_point.subdir))

        # deal with CLASSPATH
        # This has to be added here as it is benchmark specific
        cur_classpath = os.environ.get("CLASSPATH", "")
        paths = cur_classpath.split(os.pathsep)
        paths.append(ITERATIONS_RUNNER_DIR)
        paths.append(bench_dir)

        new_env = BASE_ENV.copy()
        new_env.update({"CLASSPATH": os.pathsep.join(paths)})

        args = [self.vm_path] + self.extra_vm_args + [self.iterations_runner, entry_point.target, str(iterations), str(param)]
        return self._run_exec(args, heap_lim_k, bench_env=new_env)

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
    def __init__(self, vm_path, java_home, extra_env=None):
        java_env = {"JAVA_HOME": java_home, "DEFAULT_VM": "server"}
        if extra_env is None:
            extra_env = java_env
        else:
            extra_env.update(java_env)

        JavaVMDef.__init__(self, vm_path, extra_env)
        self.extra_vm_args.insert(0, "vm") # must come first!

    def sanity_checks(self):
        JavaVMDef.sanity_checks(self)

        if not self.vm_path.endswith("mx"):
            fatal("Graal vm_path should be a path to 'mx'")

class PythonVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.py",
                                       extra_env=extra_env)

    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        # heap_lim_k unused.
        # Python reads the rlimit structure to decide its heap limit.
        return self._generic_scripting_run_exec(entry_point, benchmark,
                                                iterations, param, heap_lim_k)

class LuaVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.lua", extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        # I was unable to find any special switches to limit lua's heap size.
        # Looking at implementationsi:
        #  * luajit uses anonymous mmap() to allocate memory, fiddling
        #    with rlimits prior.
        #  * Stock lua doesn't seem to do anything special. Just realloc().
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class PHPVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.php", extra_env=extra_env)
        self.extra_vm_args += ["-d", lambda heap_lim_k: "memory_limit=%sK" % heap_lim_k]

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class RubyVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.rb", extra_env=extra_env)

class JRubyVMDef(RubyVMDef):
    def __init__(self, vm_path, extra_env=None):
        RubyVMDef.__init__(self, vm_path, extra_env)
        self.extra_vm_args += [lambda heap_lim_k: "-J-Xmx%sK" % heap_lim_k]

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class JRubyTruffleVMDef(JRubyVMDef):
    def __init__(self, vm_path,java_path, extra_env=None):
        java_env = {"JAVACMD": java_path}
        if extra_env is None:
            extra_env = java_env
        else:
            extra_env.update(java_env)
        JRubyVMDef.__init__(self, vm_path, extra_env)

        self.extra_vm_args += ['-X+T', '-J-server']

    def run_exec(self, interpreter, benchmark, iterations, param, heap_lim_k):
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, heap_lim_k)

class JavascriptVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js", extra_env=extra_env)


class V8VMDef(JavascriptVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js", extra_env=extra_env)

        # this is a best effort at limiting the heap space.
        # V8 has a "new" and "old" heap. I can't see a way to limit the total of the two.
        self.extra_vm_args += ["--max_old_space_size", lambda heap_lim_k: "%s" % int(heap_lim_k / 1024)] # as MB


    def run_exec(self, entry_point, benchmark, iterations, param, heap_lim_k):
        # Duplicates generic implementation. Need to pass args differently.

        script_path = os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir, entry_point.target)
        args = [self.vm_path] + self.extra_vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        return self._run_exec(args, heap_lim_k)
