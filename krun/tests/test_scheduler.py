from krun.tests.mocks import MockMailer, MockPlatform
from krun.scheduler import mean, ExecutionJob, ExecutionScheduler, JobMissingError
import krun.util

import os, pytest, subprocess
import bz2
import json


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
    sched = ExecutionScheduler("", "example_test.log",
                               "example_test.json.bz2", mailer,
                               MockPlatform(mailer), resume=True,
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
    sched = ExecutionScheduler("example.krun", "example_test.log",
                               "example_test.json.bz2", mailer,
                               MockPlatform(mailer), resume=True,
                               reboot=True, dry_run=True,
                               started_by_init=False)
    sched.build_schedule(config, None)
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
    results_json = krun.util.read_results('krun/tests/quick_results.json.bz2')
    sched = ExecutionScheduler("quick.krun", "quick_test.log",
                               "quick_test.json.bz2", mailer,
                               MockPlatform(mailer), resume=True,
                               reboot=True, dry_run=True,
                               started_by_init=False)
    sched.build_schedule(config, results_json)
    assert len(sched) == 0


def test_eta_dont_agree_with_schedule():
    """ETAs don't exist for all jobs for which there is iterations data"""

    mailer = MockMailer()
    config = krun.util.read_config('krun/tests/broken_etas.krun')
    results_json = krun.util.read_results('krun/tests/broken_etas_results.json.bz2')
    sched = ExecutionScheduler("broken_etas.krun", "broken_etas.log",
                               "broken_etas_results.json.bz2", mailer,
                               MockPlatform(mailer), resume=True,
                               reboot=False, dry_run=True,
                               started_by_init=False)
    try:
        sched.build_schedule(config, results_json)
    except SystemExit:
        pass
    else:
        assert(False)  # did not exit!


def test_run_schedule(monkeypatch):
    jso_file = "example_test.json.bz2"
    def dummy_shell_cmd(text):
        pass
    monkeypatch.setattr(subprocess, 'call', dummy_shell_cmd)
    monkeypatch.setattr(krun.util, 'run_shell_cmd', dummy_shell_cmd)
    mailer = MockMailer()
    config = krun.util.read_config('krun/tests/example.krun')
    platform = MockPlatform(mailer)
    for vm_name, vm_info in config["VMS"].items():
        vm_info["vm_def"].set_platform(platform)
    sched = ExecutionScheduler("krun/tests/example.krun", "example_test.log",
                               jso_file, mailer,
                               platform, resume=False,
                               reboot=False, dry_run=True,
                               started_by_init=False)
    sched.build_schedule(config, None)
    assert len(sched) == 8
    sched.run()
    assert len(sched) == 0

    # Type checks on what the scheduler dumped
    with bz2.BZ2File(jso_file, 'rb') as input_file:
        jso = json.loads(input_file.read())

        for k, execs in jso["data"].iteritems():
            assert type(execs) is list
            for one_exec in execs:
                assert type(one_exec) is list
                assert all([type(x) is float for x in one_exec])

        for k, execs in jso["eta_estimates"].iteritems():
            assert type(execs) is list
            assert all([type(x) is float for x in execs])

        assert type(jso["starting_temperatures"]) is list
        assert type(jso["reboots"]) is int
        assert type(jso["audit"]) is dict
        assert type(jso["config"]) is unicode

    os.unlink(jso_file)


def test_run_schedule_reboot(monkeypatch):
    def dummy_shell_cmd(text):
        pass
    def dummy_execv(text, lst):
        pass
    monkeypatch.setattr(os, 'execv', dummy_execv)
    monkeypatch.setattr(subprocess, 'call', dummy_shell_cmd)
    monkeypatch.setattr(krun.util, 'run_shell_cmd', dummy_shell_cmd)
    mailer = MockMailer()
    config = krun.util.read_config('krun/tests/example.krun')
    platform = MockPlatform(mailer)
    for vm_name, vm_info in config["VMS"].items():
        vm_info["vm_def"].set_platform(platform)
    sched = ExecutionScheduler("krun/tests/example.krun", "example_test.log",
                               "example_test.json.bz2", mailer,
                               platform, resume=True,
                               reboot=True, dry_run=True,
                               started_by_init=True)
    sched.build_schedule(config, None)
    assert len(sched) == 8
    with pytest.raises(AssertionError):
        sched.run()
    assert len(sched) == 7
    os.unlink("example_test.json.bz2")
