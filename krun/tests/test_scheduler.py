from krun.audit import Audit
from krun.config import Config
from krun.results import Results
from krun.scheduler import mean, ExecutionJob, ExecutionScheduler, JobMissingError
from krun.tests.mocks import MockMailer, MockPlatform
import krun.util

import os, pytest, subprocess


def test_mean_empty():
    with pytest.raises(ValueError):
        assert mean([]) == .0


def test_mean():
    flts = [1.0 / n for n in range(1, 11)]
    assert mean(flts) * float(len(flts)) == sum(flts)
    flts = [n / 10.0 for n in range(11)]
    assert mean(flts) * float(len(flts)) == sum(flts)


def test_add_del_job():
    mailer = MockMailer()
    sched = ExecutionScheduler(Config("krun/tests/example.krun"),  mailer,
                               MockPlatform(mailer), resume=False,
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


def test_build_schedule():
    mailer = MockMailer()
    sched = ExecutionScheduler(Config("krun/tests/example.krun"), mailer,
                               MockPlatform(mailer), resume=False,
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


def test_part_complete_schedule():
    mailer = MockMailer()
    sched = ExecutionScheduler(Config("krun/tests/quick.krun"), mailer,
                               MockPlatform(mailer), resume=True,
                               reboot=True, dry_run=True,
                               started_by_init=False)
    sched.build_schedule()
    assert len(sched) == 0


def test_etas_dont_agree_with_schedule():
    """ETAs don't exist for all jobs for which there is iterations data"""

    mailer = MockMailer()
    sched = ExecutionScheduler(Config("krun/tests/broken_etas.krun"),
                               mailer,
                               MockPlatform(mailer),
                               resume=True, reboot=False, dry_run=True,
                               started_by_init=False)
    try:
        sched.build_schedule()
    except SystemExit:
        pass
    else:
        assert False, "Krun did not exit when ETAs failed to tally with results!"


def test_run_schedule(monkeypatch):
    json_file = "krun/tests/example_results.json.bz2"
    def dummy_shell_cmd(text):
        pass
    monkeypatch.setattr(subprocess, 'call', dummy_shell_cmd)
    monkeypatch.setattr(krun.util, 'run_shell_cmd', dummy_shell_cmd)
    mailer = MockMailer()
    platform = MockPlatform(mailer)
    sched = ExecutionScheduler(Config("krun/tests/example.krun"),
                               mailer,
                               platform, resume=False,
                               reboot=False, dry_run=True,
                               started_by_init=False)
    sched.build_schedule()
    assert len(sched) == 8
    sched.run()
    assert len(sched) == 0

    results = Results(Config("krun/tests/example.krun"),
                      MockPlatform(MockMailer()),
                      results_file=json_file)
    for k, execs in results.data.iteritems():
        assert type(execs) is list
        for one_exec in execs:
            assert type(one_exec) is list
            assert all([type(x) is float for x in one_exec])

    for k, execs in results.eta_estimates.iteritems():
        assert type(execs) is list
        assert all([type(x) is float for x in execs])

    assert type(results.starting_temperatures) is list
    assert type(results.reboots) is int
    assert type(results.audit) is type(Audit(dict()))
    assert type(results.config) is type(Config())
    assert type(results.error_flag) is bool

    os.unlink(json_file)


def test_run_schedule_reboot(monkeypatch):
    def dummy_shell_cmd(text):
        pass
    def dummy_execv(text, lst):
        pass
    monkeypatch.setattr(os, "execv", dummy_execv)
    monkeypatch.setattr(subprocess, "call", dummy_shell_cmd)
    monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_shell_cmd)
    mailer = MockMailer()
    platform = MockPlatform(mailer)
    sched = ExecutionScheduler(Config("krun/tests/example.krun"),
                               mailer,
                               platform, resume=False,
                               reboot=True, dry_run=True,
                               started_by_init=True)
    sched.build_schedule()
    assert len(sched) == 8
    with pytest.raises(AssertionError):
        sched.run()
    assert len(sched) == 7
    os.unlink("krun/tests/example_results.json.bz2")
