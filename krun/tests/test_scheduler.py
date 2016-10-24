from krun.audit import Audit
from krun.config import Config
from krun.scheduler import (mean, ExecutionJob, ExecutionScheduler,
                            ManifestManager)
from krun.tests import BaseKrunTest
import krun.util

import os, pytest
from krun.tests import TEST_DIR


class TestReboot(Exception):
    pass

def type_check_results(results):
    for k, execs in results.wallclock_times.iteritems():
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


def make_reboot_raise(monkeypatch):
    def dummy_do_reboot(self):
        from logging import info
        info("SIMULATED: reboot via exception")
        raise TestReboot()
    monkeypatch.setattr(ExecutionScheduler, '_do_reboot', dummy_do_reboot)


def run_with_captured_reboots(config, platform, monkeypatch):
    """Runs a session to completion using exceptions to capture reboots

    Returns the number of reboots and the last scheduler"""

    make_reboot_raise(monkeypatch)
    krun.util.assign_platform(config, platform)
    reboots = 0
    while True:
        on_first_invocation = True
        if reboots > 0:
            on_first_invocation = False

        sched = ExecutionScheduler(config, platform.mailer, platform, dry_run=True,
                                   on_first_invocation=on_first_invocation)
        try:
            sched.run()
        except TestReboot:
            reboots += 1
        else:
            # normal exit() from run -- schedule finished
            break

    return reboots, sched


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

    def test_run_schedule0001(self, monkeypatch, mock_platform):
        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert sched.manifest.total_num_execs == 1
        assert sched.manifest.num_execs_left == 0
        assert n_reboots == 1

        results = sched.results
        type_check_results(results)

        assert len(results.wallclock_times) == 1  # 1 benchmark, 1 vm
        for key, execs in results.wallclock_times.iteritems():
            assert len(execs) == 1
            for _exec in execs:
                assert len(_exec) == 0  # due to dry run

        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

    def test_run_schedule0002(self, mock_platform, monkeypatch):
        config = Config(os.path.join(TEST_DIR, "example.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 8  # 2 benchmarks, 2 vms, 2 execs

        results = sched.results
        type_check_results(results)

        assert len(results.wallclock_times) == 4  # 2 benchmarks, 2 vms
        for key, execs in results.wallclock_times.iteritems():
            assert len(execs) == 2
            for _exec in execs:
               assert len(_exec) == 0  # due to dry run

        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

    def test_run_schedule0003(self, mock_platform, monkeypatch):
        config = Config(os.path.join(TEST_DIR, "example_all_skip.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 0 # all skipped!
        os.unlink(ManifestManager.PATH)

    def test_run_schedule0004(self, mock_platform, monkeypatch):
        config = Config(os.path.join(TEST_DIR, "example_skip_1vm.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 4  # 2 benchmarks, 2 vms, 2 execs, one VM skipped

        results = sched.results
        type_check_results(results)

        assert len(results.wallclock_times) == 4  # 2 benchmarks, 2 vms
        for key, execs in results.wallclock_times.iteritems():
            if "CPython" in key:
                assert len(execs) == 0
            else:
                assert len(execs) == 2

            for _exec in execs:
                assert len(_exec) == 0  # due to dry run

        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

    def test_run_schedule0005(self, mock_platform, monkeypatch):

        def dummy_execjob_run(self, mailer, dryrun=False):
            return self.empty_measurements, {}, "E"  # pretend jobs fail
        monkeypatch.setattr(ExecutionJob, 'run', dummy_execjob_run)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 8  # 2 benchmarks, 2 vms, 2 execs

        results = sched.results
        type_check_results(results)

        assert len(results.wallclock_times) == 4  # 2 benchmarks, 2 vms
        for key, execs in results.wallclock_times.iteritems():
            assert len(execs) == 2

            for _exec in execs:
                assert len(_exec) == 0  # due to error

        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

    def test_pre_and_post_exec_cmds0001(self, monkeypatch, mock_platform):
        cap_cmds = []
        def dummy_run_shell_cmd(cmd, failure_fatal=False, extra_env=None):
            cap_cmds.append(cmd)
            return "", "", 0

        monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_run_shell_cmd)

        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        config.PRE_EXECUTION_CMDS = ["cmd1", "cmd2"]
        config.POST_EXECUTION_CMDS = ["cmd3", "cmd4"]

        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

        assert n_reboots == 1
        expect = ["cmd1", "cmd2", "cmd3", "cmd4"]
        assert cap_cmds == expect

    def test_pre_and_post_exec_cmds0002(self, monkeypatch, mock_platform):
        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        path = os.path.join(TEST_DIR, "shell-out")
        cmd = "echo ${KRUN_RESULTS_FILE}:${KRUN_LOG_FILE} > %s" % path
        config.POST_EXECUTION_CMDS = [cmd]

        krun.util.assign_platform(config, mock_platform)
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        os.unlink(config.results_filename())

        with open(path) as fh:
            got = fh.read().strip()

        os.unlink(path)
        os.unlink(ManifestManager.PATH)

        assert n_reboots == 1
        elems = got.split(":")
        assert elems[0].endswith(".json.bz2")
        assert elems[1].endswith(".log")

    def test_pre_and_post_cmds0003(self, monkeypatch, mock_platform):
        """Check that the pre/post commands use a shell and don't just exec(3)"""

        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        tmp_file = os.path.join(TEST_DIR, "prepost.txt")

        # commands use shell syntax
        config.PRE_EXECUTION_CMDS = ["echo 'pre' > %s" % tmp_file]
        config.POST_EXECUTION_CMDS = ["echo 'post' >> %s" % tmp_file]

        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 1
        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

        with open(tmp_file) as fh:
            got = fh.read()

        os.unlink(tmp_file)
        assert got == "pre\npost\n"

    def test_boot_loop0001(self, monkeypatch, mock_platform, caplog):
        make_reboot_raise(monkeypatch)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)

        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True, on_first_invocation=True)

        # Do the initial reboot
        try:
            sched.run()
        except TestReboot:
            pass
        else:
            assert False

        # Simulate a boot loop
        sched.results.reboots = 9999  # way too many
        sched.results.write_to_file()

        # Run the first process execution
        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True, on_first_invocation=False)
        with pytest.raises(krun.util.FatalKrunError):
            sched.run()

        expect = ("HALTING now to prevent an infinite reboot loop: "
                  "INVARIANT num_reboots <= num_jobs violated. Krun was about "
                  "to execute reboot number: 10000. 1 jobs have been "
                  "completed, 7 are left to go.")
        assert expect in caplog.text()

        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)

    def test_empty_schedule0001(self, mock_platform, monkeypatch, caplog):
        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 1

        # The schedule is now empty, so this should not run anything
        def dummy_run(self, mailer, dry_run=False):
            assert False  # running a job wil cause a test failure
        monkeypatch.setattr(ExecutionJob, "run", dummy_run)

        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True, on_first_invocation=False)
        sched.run()
        assert "Empty schedule!" in caplog.text()

        os.unlink(config.results_filename())
        os.unlink(ManifestManager.PATH)
