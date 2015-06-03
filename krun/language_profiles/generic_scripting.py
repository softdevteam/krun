import os

from krun.language_profiles import BaseLanguageProfile, ITERATIONS_RUNNER_DIR

class GenericScripting(BaseLanguageProfile):
    def __init__(self, iterations_runner, entrypoint):
        BaseLanguageProfile.__init__(self, entrypoint)
        self.iterations_runner = os.path.join(ITERATIONS_RUNNER_DIR, iterations_runner)

    def run_exec(self, interpreter, benchmark, iterations, param):
        script_path = os.path.join(benchmark, self.entry_point)
        args = [interpreter, self.iterations_runner, script_path, str(iterations), str(param)]
        return self._run_exec(args, env=None)

