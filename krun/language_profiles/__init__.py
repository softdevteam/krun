import subprocess
import os

from krun import ANSI_GREEN, ANSI_RESET

DIR = os.path.abspath(os.path.dirname(__file__))
ITERATIONS_RUNNER_DIR = os.path.abspath(
    os.path.join(DIR, "..", "iteration_runners"))

class BaseLanguageProfile(object):

    def __init__(self, entry_point):
        self.entry_point = entry_point

    def run_exec(self, interpreter, benchmark, iterations, param):
        raise NotImplemented("abstract")

    def _run_exec(self, args, env=None):
        if os.environ.get("BENCH_DEBUG"):
            print("%s    DEBUG: cmdline='%s'%s" % (ANSI_GREEN, " ".join(args), ANSI_RESET))
            print("%s    DEBUG: env='%s'%s" % (ANSI_GREEN, env, ANSI_RESET))

        if os.environ.get("BENCH_DRYRUN") != None:
            print("%s    DEBUG: %s%s" % (ANSI_GREEN, "DRY RUN, SKIP", ANSI_RESET))
            return "[]"

        stdout, stderr = subprocess.Popen(
                args, stdout=subprocess.PIPE).communicate()
        return stdout

