from krun.audit import Audit
from krun.config import Config
from krun.results import Results
from krun.scheduler import mean, ExecutionJob, ExecutionScheduler, JobMissingError
from krun.tests import BaseKrunTest
import krun.util

import os, pytest, subprocess
from krun.tests import TEST_DIR

class TestScheduler(BaseKrunTest):
    """Test the job scheduler."""

    def test_mean_empty(self):
        with pytest.raises(ValueError):
            assert mean([]) == .0


    def test_mean(self):
        flts = [1.0 / n for n in range(1, 11)]
        assert mean(flts) * float(len(flts)) == sum(flts)
        flts = [n / 10.0 for n in range(11)]
        assert mean(flts) * float(len(flts)) == sum(flts)


    def test_add_del_job(self, mock_platform):
        sched = ExecutionScheduler(Config(os.path.join(TEST_DIR, "example.krun")),
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   reboot=True, dry_run=False,
                                   started_by_init=False)
        assert len(sched) == 0
        sched.add_job(ExecutionJob(sched, "CPython", "", "mybench",
                                   "default-python", 1000))
        assert len(sched) == 1
        sched.remove_job_by_key("mybench:CPython:default-python")
        assert len(sched) == 0
        with pytest.raises(JobMissingError):
            sched.remove_job_by_key("mybench:HHVM:default-php")


    def test_build_schedule(self, mock_platform):
        sched = ExecutionScheduler(Config(os.path.join(TEST_DIR, "example.krun")),
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   reboot=True, dry_run=True,
                                   started_by_init=False)
        sched.build_schedule()
        assert len(sched) == 8
        dummy_py = ExecutionJob(sched, "CPython", "", "dummy",
                                "default-python", 1000)
        dummy_java = ExecutionJob(sched, "Java", "", "dummy", "default-java", 1000)
        nbody_py = ExecutionJob(sched, "CPython", "", "nbody",
                                "default-python", 1000)
        nbody_java = ExecutionJob(sched, "Java", "", "nbody", "default-java", 1000)
        assert sched.work_deque.count(dummy_py) == 2
        assert sched.work_deque.count(dummy_java) == 2
        assert sched.work_deque.count(nbody_py) == 2
        assert sched.work_deque.count(nbody_java) == 2


    def test_part_complete_schedule(self, mock_platform):
        sched = ExecutionScheduler(Config(os.path.join(TEST_DIR, "quick.krun")),
                                   mock_platform.mailer,
                                   mock_platform, resume=True,
                                   reboot=True, dry_run=True,
                                   started_by_init=False)
        sched.build_schedule()
        assert len(sched) == 0


    def test_etas_dont_agree_with_schedule(self, mock_platform):
        """ETAs don't exist for all jobs for which there is iterations data"""

        sched = ExecutionScheduler(Config(os.path.join(TEST_DIR, "broken_etas.krun")),
                                   mock_platform.mailer, mock_platform,
                                   resume=True, reboot=False, dry_run=True,
                                   started_by_init=False)
        try:
            sched.build_schedule()
        except krun.util.FatalKrunError:
            pass
        else:
            assert False, "Krun did not exit when ETAs failed to tally with results!"


    def test_run_schedule(self, monkeypatch, mock_platform):
        json_file = os.path.join(TEST_DIR, "example_results.json.bz2")
        def dummy_shell_cmd(text):
            pass
        monkeypatch.setattr(subprocess, 'call', dummy_shell_cmd)
        monkeypatch.setattr(krun.util, 'run_shell_cmd', dummy_shell_cmd)
        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        sched = ExecutionScheduler(config,
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   reboot=False, dry_run=True,
                                   started_by_init=False)
        sched.build_schedule()
        assert len(sched) == 8
        sched.run()
        assert len(sched) == 0

        results = Results(Config(os.path.join(TEST_DIR, "example.krun")),
                          mock_platform, results_file=json_file)

        for k, execs in results.data.iteritems():
            assert type(execs) is list
            for one_exec in execs:
                assert type(one_exec) is list
                assert all([type(x) is float for x in one_exec])

        for k, execs in results.eta_estimates.iteritems():
            assert type(execs) is list
            assert all([type(x) is float for x in execs])

        assert type(results.starting_temperatures) is dict
        assert type(results.reboots) is int
        assert type(results.audit) is type(Audit(dict()))
        assert type(results.config) is type(Config())
        assert type(results.error_flag) is bool

        os.unlink(json_file)


    def test_run_schedule_reboot(self, monkeypatch, mock_platform):
        def dummy_shell_cmd(text):
            pass
        def dummy_execv(text, lst):
            pass
        monkeypatch.setattr(os, "execv", dummy_execv)
        monkeypatch.setattr(subprocess, "call", dummy_shell_cmd)
        monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_shell_cmd)
        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        sched = ExecutionScheduler(config,
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   reboot=True, dry_run=True,
                                   started_by_init=True)
        sched.build_schedule()
        assert len(sched) == 8
        with pytest.raises(AssertionError):
            sched.run()
        assert len(sched) == 7
        os.unlink(os.path.join(TEST_DIR, "example_results.json.bz2"))

    def test_queue_len0001(self, mock_platform):
        config_path = os.path.join(TEST_DIR, "more_complicated.krun")
        sched = ExecutionScheduler(Config(config_path),
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   reboot=True, dry_run=False,
                                   started_by_init=False)
        sched.build_schedule()
        assert len(sched) == 90  # taking into account skips


    def test_pre_exec_cmds0001(self, monkeypatch, mock_platform):
        cap_cmds = []
        def dummy_run_shell_cmd(cmd, failure_fatal=False, extra_env=None):
            cap_cmds.append(cmd)
            return "", "", 0

        monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_run_shell_cmd)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        config.PRE_EXECUTION_CMDS = ["cmd1", "cmd2"]
        krun.util.assign_platform(config, mock_platform)

        sched = ExecutionScheduler(config,
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   dry_run=True,
                                   started_by_init=True)
        sched.build_schedule()
        assert len(sched) == 8
        sched.run()

        expect = ["cmd1", "cmd2"] * 8
        assert cap_cmds == expect

    def test_post_exec_cmds0001(self, monkeypatch, mock_platform):
        cap_cmds = []
        def dummy_run_shell_cmd(cmd, failure_fatal=False, extra_env=None):
            cap_cmds.append(cmd)
            return "", "", 0

        monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_run_shell_cmd)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        config.POST_EXECUTION_CMDS = ["cmd1", "cmd2"]
        krun.util.assign_platform(config, mock_platform)

        sched = ExecutionScheduler(config,
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   dry_run=True,
                                   started_by_init=True)
        sched.build_schedule()
        assert len(sched) == 8
        sched.run()

        expect = ["cmd1", "cmd2"] * 8
        assert cap_cmds == expect

    def test_post_exec_cmds0002(self, monkeypatch, mock_platform):
        config = Config(os.path.join(TEST_DIR, "example.krun"))
        path = os.path.join(TEST_DIR, "shell-out")
        cmd = "echo ${KRUN_RESULTS_FILE}:${KRUN_LOG_FILE} > %s" % path
        config.POST_EXECUTION_CMDS = [cmd]
        krun.util.assign_platform(config, mock_platform)

        sched = ExecutionScheduler(config,
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   dry_run=True,
                                   started_by_init=True)
        sched.build_schedule()
        assert len(sched) == 8
        sched.run()

        with open(path) as fh:
            got = fh.read().strip()

        os.unlink(path)

        elems = got.split(":")

        assert elems[0].endswith(".json.bz2")
        assert elems[1].endswith(".log")

    def test_pre_and_post_cmds0001(self, monkeypatch, mock_platform):
        cap_cmds = []
        def dummy_run_shell_cmd(cmd, failure_fatal=False, extra_env=None):
            cap_cmds.append(cmd)
            return "", "", 0

        monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_run_shell_cmd)

        config = Config(os.path.join(TEST_DIR, "example.krun"))

        config.PRE_EXECUTION_CMDS = ["pre1", "pre2"]
        config.POST_EXECUTION_CMDS = ["post1", "post2"]

        krun.util.assign_platform(config, mock_platform)

        sched = ExecutionScheduler(config,
                                   mock_platform.mailer,
                                   mock_platform, resume=False,
                                   dry_run=True,
                                   started_by_init=True)
        sched.build_schedule()
        assert len(sched) == 8
        sched.run()

        expect = ["pre1", "pre2", "post1", "post2"] * 8
        assert cap_cmds == expect
