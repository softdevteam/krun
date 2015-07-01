import subprocess
import os

from krun import ANSI_GREEN, ANSI_RESET

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = "benchmarks"

# !!!
# Don't mutate any lists passed down from the user's config file!
# !!!

class BaseVariant(object):

    def __init__(self, iterations_runner, entry_point=None, subdir=None, extra_env=None):
        assert entry_point is not None
        if subdir is None:
            subdir = "."
        if extra_env is None:
            extra_env = {}
        self.entry_point = entry_point
        self.iterations_runner = iterations_runner
        self.subdir = subdir
        self.extra_env = extra_env

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
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

class GenericScriptingVariant(BaseVariant):
    def __init__(self, iterations_runner, entry_point=None, subdir=None, extra_env=None):
        fp_iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)
        BaseVariant.__init__(self,
                             fp_iterations_runner,
                             entry_point=entry_point,
                             subdir=subdir,
                             extra_env=extra_env)

    def _generic_scripting_run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args):
        script_path = os.path.join(BENCHMARKS_DIR, benchmark, self.subdir, self.entry_point)
        args = [interpreter] + vm_args + [self.iterations_runner, script_path, str(iterations), str(param)]

        use_env = os.environ.copy()
        use_env.update(vm_env)

        return self._run_exec(args, use_env)

class JavaVariant(BaseVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        BaseVariant.__init__(self,
                             "IterationsRunner",
                             entry_point=entry_point,
                             subdir=subdir,
                             extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        vm_args = vm_args[:] + ["-Xmx%sK" % heap_limit_kb]
        args = [interpreter] + vm_args + [self.iterations_runner, self.entry_point, str(iterations), str(param)]
        bench_dir = os.path.abspath(os.path.join(os.getcwd(), BENCHMARKS_DIR, benchmark, self.subdir))

        # deal with CLASSPATH
        cur_classpath = os.environ.get("CLASSPATH", "")
        paths = cur_classpath.split(os.pathsep)
        paths.append(ITERATIONS_RUNNER_DIR)
        paths.append(bench_dir)

        new_env = os.environ.copy()
        new_env["CLASSPATH"] = os.pathsep.join(paths)
        new_env.update(vm_env)

        return self._run_exec(args, new_env)


class PythonVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.py",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        # heap_limit_kb unused.
        # Python reads the rlimit structure to decide its heap limit.
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class LuaVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.lua",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        # I was unable to find any special switches to limit lua's heap size.
        # Looking at implementationsi:
        #  * luajit uses anonymous mmap() to allocate memory, fiddling
        #    with rlimits prior.
        #  * Stock lua doesn't seem to do anything special. Just realloc().
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class PHPVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.php",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        vm_args = vm_args[:] + ["-d", "memory_limit=%sK" % heap_limit_kb]
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class RubyVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.rb",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

class JRubyVariant(RubyVariant):
    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):
        vm_args = vm_args[:] + ["-J-Xmx%sK" % heap_limit_kb]
        return self._generic_scripting_run_exec(interpreter, benchmark, iterations, param, vm_env, vm_args)

class JavascriptVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.js",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)


class V8Variant(JavascriptVariant):
    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args, heap_limit_kb):

        # this is a best effort at limiting the heap space.
        # V8 has a "new" and "old" heap. I can't see a way to limit the total of the two.
        vm_args = vm_args[:] + ["--max_old_space_size", "%s" % int(heap_limit_kb / 1024)] # as MB

        script_path = os.path.join(BENCHMARKS_DIR, benchmark, self.subdir, self.entry_point)
        args = [interpreter] + vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        use_env = os.environ.copy()
        use_env.update(vm_env)

        return self._run_exec(args, use_env)
