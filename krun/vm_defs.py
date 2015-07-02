import subprocess
import os

from krun import ANSI_GREEN, ANSI_RESET

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = "benchmarks"

# !!!
# Don't mutate any lists passed down from the user's config file!
# !!!

class BaseVMDef(object):

    def __init__(self, iterations_runner, extra_env=None):
        self.iterations_runner = iterations_runner
        if extra_env is None:
            extra_env = {}
        self.extra_env = extra_env
        # tempting as it is to add a self.vm_path, we don't. If we were to add
        # natively compiled languages, then there is no "VM" to speak of.

    def run_exec(self, entry_point, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        raise NotImplementedError("abstract")

    def _run_exec(self, args, env=None):
        """ Deals with actually shelling out """
        if env is not None:
            use_env = env.copy()
        else:
            use_env = {}
        use_env.update(self.extra_env)

        if os.environ.get("BENCH_DEBUG"):
            print("%s    DEBUG: cmdline='%s'%s" % (ANSI_GREEN, " ".join(args), ANSI_RESET))
            print("%s    DEBUG: env='%s'%s" % (ANSI_GREEN, env, ANSI_RESET))

        if os.environ.get("BENCH_DRYRUN") != None:
            print("%s    DEBUG: %s%s" % (ANSI_GREEN, "DRY RUN, SKIP", ANSI_RESET))
            return "[]"

        stdout, stderr = subprocess.Popen(
                args, stdout=subprocess.PIPE, env=env).communicate()
        return stdout

class GenericScriptingVMDef(BaseVMDef):
    def __init__(self, vm_path, iterations_runner, entry_point=None, subdir=None, extra_env=None):
        self.vm_path = vm_path
        fp_iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)
        BaseVMDef.__init__(self, fp_iterations_runner, extra_env=extra_env)

    def _generic_scripting_run_exec(self, entry_point, benchmark, iterations, param, vm_env, vm_args):
        script_path = os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir, entry_point.target)
        args = [self.vm_path] + vm_args + [self.iterations_runner, script_path, str(iterations), str(param)]

        use_env = os.environ.copy()
        use_env.update(vm_env)

        return self._run_exec(args, use_env)

class JavaVMDef(BaseVMDef):
    def __init__(self, vm_path, extra_env=None):
        self.vm_path = vm_path
        BaseVMDef.__init__(self, "IterationsRunner", extra_env=extra_env)

    def run_exec(self, entry_point, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        vm_args = vm_args[:] + ["-Xmx%sK" % heap_limit_kb]
        args = [self.vm_path] + vm_args + [self.iterations_runner, entry_point.target, str(iterations), str(param)]
        bench_dir = os.path.abspath(os.path.join(os.getcwd(), BENCHMARKS_DIR, benchmark, entry_point.subdir))

        # deal with CLASSPATH
        cur_classpath = os.environ.get("CLASSPATH", "")
        paths = cur_classpath.split(os.pathsep)
        paths.append(ITERATIONS_RUNNER_DIR)
        paths.append(bench_dir)

        new_env = os.environ.copy()
        new_env["CLASSPATH"] = os.pathsep.join(paths)
        new_env.update(vm_env)

        return self._run_exec(args, new_env)

class PythonVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.py",
                                       extra_env=extra_env)

    def run_exec(self, entry_point, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        # heap_limit_kb unused.
        # Python reads the rlimit structure to decide its heap limit.
        return self._generic_scripting_run_exec(entry_point, benchmark, iterations, param, vm_env, vm_args)

class LuaVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.lua", extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        # I was unable to find any special switches to limit lua's heap size.
        # Looking at implementationsi:
        #  * luajit uses anonymous mmap() to allocate memory, fiddling
        #    with rlimits prior.
        #  * Stock lua doesn't seem to do anything special. Just realloc().
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class PHPVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.php", extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        vm_args = vm_args[:] + ["-d", "memory_limit=%sK" % heap_limit_kb]
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class RubyVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.rb", extra_env=extra_env)

class JRubyVMDef(RubyVMDef):
    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        vm_args = vm_args[:] + ["-J-Xmx%sK" % heap_limit_kb]
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class JavascriptVMDef(GenericScriptingVMDef):
    def __init__(self, vm_path, extra_env=None):
        GenericScriptingVMDef.__init__(self, vm_path, "iterations_runner.js", extra_env=extra_env)


class V8VMDef(JavascriptVMDef):
    def run_exec(self, entry_point, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):

        # this is a best effort at limiting the heap space.
        # V8 has a "new" and "old" heap. I can't see a way to limit the total of the two.
        vm_args = vm_args[:] + ["--max_old_space_size", "%s" % int(heap_limit_kb / 1024)] # as MB

        script_path = os.path.join(BENCHMARKS_DIR, benchmark, entry_point.subdir, entry_point.target)
        args = [self.vm_path] + vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        use_env = os.environ.copy()
        use_env.update(vm_env)

        return self._run_exec(args, use_env)
