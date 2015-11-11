from krun import LOGFILE_FILENAME_TIME_FORMAT
from krun.util import (should_skip, format_raw_exec_results, output_name,
                       log_and_mail, log_name, fatal, read_config,
                       run_shell_cmd, read_results, dump_results,
                       check_and_parse_execution_results,
                       audits_same_platform, ExecutionFailed)
from krun.tests.mocks import MockMailer

import bz2, json, os, pytest, time


def test_should_skip():
    config = dict([("SKIP", ["*:PyPy:*",
                             "*:CPython:*",
                             "*:Hotspot:*",
                             "*:Graal:*",
                             "*:LuaJIT:*",
                             "*:HHVM:*",
                             "*:JRubyTruffle:*",
                             "*:V8:*",
    ])])
    assert should_skip(config, "nbody:HHVM:default-php")
    assert not should_skip(dict([("SKIP", [])]), "nbody:HHVM:default-php")


def test_read_config():
    path = "examples/example.krun"
    config = read_config(path)
    assert config is not None
    assert config["BENCHMARKS"] == {"dummy": 1000, "nbody": 1000}
    assert config["N_EXECUTIONS"] == 2
    assert config["SKIP"] == []
    assert config["MAIL_TO"] == []
    assert config["ITERATIONS_ALL_VMS"] == 5
    assert config["HEAP_LIMIT"] == 2097152


def test_read_corrupt_config():
    path = "krun/tests/corrupt.krun"
    with pytest.raises(Exception):
        _ = read_config(path)


def test_output_name():
    assert output_name(".krun") == "_results.json.bz2"
    assert output_name("example.krun") == "example_results.json.bz2"


def test_log_name(monkeypatch):
    tstamp = time.strftime(LOGFILE_FILENAME_TIME_FORMAT)
    assert log_name("example.krun", False) == "example" + "_" + tstamp + ".log"
    assert log_name(".krun", False) == "_" + tstamp + ".log"
    def mock_mtime(path):
        return 1445964109.9363003
    monkeypatch.setattr(os.path, 'getmtime', mock_mtime)
    tstamp = '20151027_164149'
    assert log_name("example.krun", True) == "example" + "_" + tstamp + ".log"
    assert log_name(".krun", True) == "_" + tstamp + ".log"


def test_fatal(capsys):
    msg = "example text"
    with pytest.raises(SystemExit):
        fatal(msg)
        out, err = capsys.readouterr()
        assert out == ""
        assert err == "ERROR:root:" + msg + "\n"


def test_log_and_mail():
    log_fn = lambda s: None
    log_and_mail(MockMailer(), log_fn, "subject", "msg", exit=False,
                 bypass_limiter=False)
    with pytest.raises(SystemExit):
        log_and_mail(MockMailer(), log_fn, "", "", exit=True,
                     bypass_limiter=False)
    assert True


def test_format_raw():
    assert format_raw_exec_results([]) == []
    data = [1.33333344444, 4.555555666]
    expected = [1.333333, 4.555556]
    assert format_raw_exec_results(data) == expected


def test_run_shell_cmd():
    msg = "example text"
    out, err, rc = run_shell_cmd("echo " + msg)
    assert out == msg
    assert err == ""
    assert rc == 0


def test_run_shell_cmd_fatal(capsys):
    cmd = "nonsensecommand"
    with pytest.raises(SystemExit):
        out, err, rc = run_shell_cmd(cmd)
        assert rc != 0
        assert err == cmd + ": command not found"
        assert out == ""


def test_read_results():
    results = read_results('krun/tests/quick_results.json.bz2')
    expected = {u'nbody:CPython:default-python': [[0.022256]],
                u'dummy:CPython:default-python': [[1.005115]],
                u'nbody:Java:default-java': [[26.002632]],
                u'dummy:Java:default-java': [[1.000941]]}
    with open('krun/tests/quick.krun', 'rb') as config_fp:
        config = config_fp.read()
    assert results['config'] == config
    assert results['audit']['uname'] == u'Linux'
    assert results['audit']['debian_version'] == u'jessie/sid'
    assert results['data'] == expected
    assert results['starting_temperatures'] == [4355, 9879]
    assert results['eta_estimates'] == \
        {
            u'nbody:CPython:default-python': [0.022256],
            u'dummy:CPython:default-python': [1.005115],
            u'nbody:Java:default-java': [26.002632],
            u'dummy:Java:default-java': [1.000941]
        }


def test_dump_results():

    class DummyPlatform(object):
        audit = 'example audit (py.test)'
        starting_temperatures = [4355, 9879]

    class DummyExecutionScheduler(object):
        platform = DummyPlatform()
        out_file = output_name("krun/tests/example.krun")
        results = {'dummy:Java:default-java': [[1.000726]]}
        nreboots = 5
        eta_estimates = {'dummy:Java:default-java': [1.1]}
        error_flag = False
        config_file = 'krun/tests/example.krun'

    dummy_sched = DummyExecutionScheduler()
    dump_results(dummy_sched)

    with open(dummy_sched.config_file, 'r') as config_fp:
        config = config_fp.read()
        with bz2.BZ2File(dummy_sched.out_file, 'rb') as input_file:
            dumped_results = json.loads(input_file.read())
            assert dumped_results['audit'] == dummy_sched.platform.audit
            assert dumped_results['starting_temperatures'] == \
                dummy_sched.platform.starting_temperatures
            assert dumped_results['config'] == config
            assert dumped_results['data'] == dummy_sched.results
            assert dumped_results['reboots'] == dummy_sched.nreboots
            assert dumped_results['eta_estimates'] == \
                dummy_sched.eta_estimates
            assert dumped_results['error_flag'] == dummy_sched.error_flag
        os.unlink(dummy_sched.out_file)  # Clean-up generated file.


def test_check_and_parse_execution_results():
    stdout = "[0.000403]"
    stderr = "[iterations_runner.py] iteration 1/1"
    assert check_and_parse_execution_results(stdout, stderr, 0) == json.loads(stdout)
    # Non-zero return code.
    with pytest.raises(ExecutionFailed) as excinfo:
        check_and_parse_execution_results(stdout, stderr, 1)
    expected = """Benchmark returned non-zero or didn't emit JSON list. return code: 1
stdout:
--------------------------------------------------
[0.000403]
--------------------------------------------------

stderr:
--------------------------------------------------
[iterations_runner.py] iteration 1/1
--------------------------------------------------
"""
    assert excinfo.value.message == expected
    # Corrupt Json in STDOUT.
    with pytest.raises(ExecutionFailed) as excinfo:
        check_and_parse_execution_results("[0.000403[", stderr, 0)
    expected = """Benchmark returned non-zero or didn't emit JSON list. Exception string: Expecting , delimiter: line 1 column 10 (char 9)
return code: 0
stdout:
--------------------------------------------------
[0.000403[
--------------------------------------------------

stderr:
--------------------------------------------------
[iterations_runner.py] iteration 1/1
--------------------------------------------------
"""
    assert excinfo.value.message == expected


def test_audit_compare():
    audit0 = dict([("cpuinfo", u"processor\t: 0\nvendor_id\t: GenuineIntel"),
                   ("uname", u"Linux"),
                   ("debian_version", u"jessie/sid"),
                   ("packages", u"1:1.2.8.dfsg-2ubuntu1"),
                   ("dmesg", u"")])
    audit1 = dict([("cpuinfo", u"processor\t: 0\nvendor_id\t: GenuineIntel"),
                   ("uname", u"BSD"),
                   ("packages", u"1:1.2.8.dfsg-2ubuntu1"),
                   ("dmesg", u"")])
    assert audits_same_platform(audit0, audit0)
    assert audits_same_platform(audit1, audit1)
    assert not audits_same_platform([], [])
    assert not audits_same_platform(audit0, audit1)
    assert not audits_same_platform(audit1, audit0)
