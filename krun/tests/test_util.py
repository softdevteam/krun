from krun.util import (format_raw_exec_results,
                       log_and_mail, fatal,
                       check_and_parse_execution_results,
                       run_shell_cmd, audits_same_platform,
                       ExecutionFailed)
from krun.tests.mocks import MockMailer

import json
import pytest


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
