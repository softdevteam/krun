import subprocess
import os

from krun import ANSI_GREEN, ANSI_RESET

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(os.path.join(DIR, "..", "iterations_runners"))
BENCHMARKS_DIR = "benchmarks"

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

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args):
        raise NotImplemented("abstract")

    def _run_exec(self, args, env=None):
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

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args):
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

    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args):
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

class LuaVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.lua",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

class PHPVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.php",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

class RubyVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.rb",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

class JavascriptVariant(GenericScriptingVariant):
    def __init__(self, entry_point=None, subdir=None, extra_env=None):
        GenericScriptingVariant.__init__(self,
                                         "iterations_runner.js",
                                         entry_point=entry_point,
                                         subdir=subdir,
                                         extra_env=extra_env)

    # pretty much the same as the generic implementation, but needs a '--' argument.
    def run_exec(self, interpreter, benchmark, iterations, param, vm_env, vm_args):
        script_path = os.path.join(BENCHMARKS_DIR, benchmark, self.subdir, self.entry_point)
        args = [interpreter] + vm_args + \
            [self.iterations_runner, '--', script_path, str(iterations), str(param)]

        use_env = os.environ.copy()
        use_env.update(vm_env)

        return self._run_exec(args, use_env)
