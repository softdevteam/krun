from krun.tests.mocks import MockMailer, MockPlatform
from krun.results import Results
from krun.scheduler import mean, ExecutionJob, ExecutionScheduler, JobMissingError
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
    sched = ExecutionScheduler(None, "example_test.log",
                               "krun/tests/example_test.json.bz2", mailer,
                               MockPlatform(mailer), resume=False,
                               reboot=True, dry_run=False,
                               started_by_init=False)
    assert len(sched) == 0
    sched.add_job(ExecutionJob(sched, None, "CPython", "", "mybench",
                               "default-python", 1000))
    assert len(sched) == 1
    sched.remove_job_by_key("mybench:CPython:default-python")
    assert len(sched) == 0
    with pytest.raises(JobMissingError):
        sched.remove_job_by_key("mybench:HHVM:default-php")


def test_build_schedule():
    mailer = MockMailer()
    config = krun.util.read_config('krun/tests/example.krun')
    sched = ExecutionScheduler("krun/tests/example.krun", "example_test.log",
                               "krun/tests/example_test.json.bz2", mailer,
                               MockPlatform(mailer), resume=False,
                               reboot=True, dry_run=True,
                               started_by_init=False)
    sched.build_schedule(config)
    assert len(sched) == 8
    dummy_py = ExecutionJob(sched, config, "CPython", "", "dummy",
                            "default-python", 1000)
    dummy_java = ExecutionJob(sched, config, "Java", "", "dummy",
                              "default-java", 1000)
    nbody_py = ExecutionJob(sched, config, "CPython", "", "nbody",
                            "default-python", 1000)
    nbody_java = ExecutionJob(sched, config, "Java", "", "nbody",
                              "default-java", 1000)
    assert sched.work_deque.count(dummy_py) == 2
    assert sched.work_deque.count(dummy_java) == 2
    assert sched.work_deque.count(nbody_py) == 2
    assert sched.work_deque.count(nbody_java) == 2


def test_part_complete_schedule():
    mailer = MockMailer()
    config = krun.util.read_config('krun/tests/quick.krun')
    sched = ExecutionScheduler("krun/tests/quick.krun", "krun/tests/quick_test.log",
                               "krun/tests/quick_results.json.bz2", mailer,
                               MockPlatform(mailer), resume=True,
                               reboot=True, dry_run=True,
                               started_by_init=False)
    sched.build_schedule(config)
    assert len(sched) == 0


def test_etas_dont_agree_with_schedule():
    """ETAs don't exist for all jobs for which there is iterations data"""

    mailer = MockMailer()
    config = krun.util.read_config("krun/tests/broken_etas.krun")
    sched = ExecutionScheduler("krun/tests/broken_etas.krun",
                               "krun/tests/broken_etas.log",
                               "krun/tests/broken_etas_results.json.bz2",
                               mailer,
                               MockPlatform(mailer),
                               resume=True, reboot=False, dry_run=True,
                               started_by_init=False)
    try:
        sched.build_schedule(config)
    except SystemExit:
        pass
    else:
        assert False, "Krun did not exit when ETAs failed to tally with results!"


def test_run_schedule(monkeypatch):
    json_file = "krun/tests/test_run_schedule.json.bz2"
    def dummy_shell_cmd(text):
        pass
    monkeypatch.setattr(subprocess, 'call', dummy_shell_cmd)
    monkeypatch.setattr(krun.util, 'run_shell_cmd', dummy_shell_cmd)
    mailer = MockMailer()
    config = krun.util.read_config("krun/tests/example.krun")
    platform = MockPlatform(mailer)
    for vm_name, vm_info in config["VMS"].items():
        vm_info["vm_def"].set_platform(platform)
    sched = ExecutionScheduler("krun/tests/example.krun", "example_test.log",
                               json_file, mailer,
                               platform, resume=False,
                               reboot=False, dry_run=True,
                               started_by_init=False)
    sched.build_schedule(config)
    assert len(sched) == 8
    sched.run()
    assert len(sched) == 0

    results = Results(results_file=json_file)
    for k, execs in results.data.iteritems():
        assert type(execs) is list
        for one_exec in execs:
            assert type(one_exec) is list
            assert all([type(x) is float for x in one_exec])

    for k, execs in results.etas.iteritems():
        assert type(execs) is list
        assert all([type(x) is float for x in execs])

    assert type(results.starting_temperatures) is list
    assert type(results.reboots) is int
    assert type(results.audit) is dict
    assert type(results.config) is unicode
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
    config = krun.util.read_config("krun/tests/example.krun")
    platform = MockPlatform(mailer)
    for vm_name, vm_info in config["VMS"].items():
        vm_info["vm_def"].set_platform(platform)
    sched = ExecutionScheduler("krun/tests/example.krun",
                               "krun/test/sexample_test.log",
                               "krun/tests/example_test.json.bz2",
                               mailer,
                               platform, resume=False,
                               reboot=True, dry_run=True,
                               started_by_init=True)
    sched.build_schedule(config)
    assert len(sched) == 8
    with pytest.raises(AssertionError):
        sched.run()
    assert len(sched) == 7
    os.unlink("krun/tests/example_test.json.bz2")
