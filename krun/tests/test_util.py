from krun.util import (format_raw_exec_results, log_and_mail, fatal,
                       check_and_parse_execution_results, run_shell_cmd,
                       run_shell_cmd_bench, get_git_version, ExecutionFailed,
                       get_session_info, run_shell_cmd_list, FatalKrunError,
                       stash_envlog, dump_instr_json)
from krun.tests.mocks import MockMailer, mock_platform
from krun.tests import TEST_DIR
from krun.config import Config
from krun.scheduler import ManifestManager
from krun.tests.mocks import mock_platform, mock_manifest, mock_mailer
from bz2 import BZ2File

import json
import logging
import pytest
import os
from tempfile import NamedTemporaryFile


def test_fatal(capsys, caplog):
    caplog.setLevel(logging.ERROR)
    msg = "example text"
    with pytest.raises(FatalKrunError):
        fatal(msg)
    out, err = capsys.readouterr()
    assert out == ""
    assert msg in caplog.text()


def test_log_and_mail(mock_manifest, mock_mailer):
    log_fn = lambda s: None
    log_and_mail(mock_mailer, log_fn, "subject", "msg", exit=False,
                 bypass_limiter=False, manifest=mock_manifest)
    with pytest.raises(FatalKrunError):
        log_and_mail(MockMailer(), log_fn, "", "", exit=True,
                     bypass_limiter=False, manifest=mock_manifest)
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

    msg2 = "another example"
    out, err, rc = run_shell_cmd("(>&2 echo %s)  && (echo %s)" % (msg2, msg))
    assert out == msg
    assert err == msg2
    assert rc == 0

def test_run_shell_cmd_fatal():
    cmd = "nonsensecommand"
    out, err, rc = run_shell_cmd(cmd, False)
    assert rc != 0
    assert cmd in err
    assert out == ""

def test_run_shell_cmd_bench():
    from krun.platform import detect_platform
    platform = detect_platform(None, None)
    msg = "example text\n"
    out, err, rc = run_shell_cmd_bench("echo " + msg, platform)
    assert out == msg
    assert err == ""
    assert rc == 0

    msg2 = "another example\n"
    out, err, rc = run_shell_cmd_bench(
        "(>&2 echo %s)  && (echo %s)" % (msg2, msg),
        platform)
    assert out == msg
    assert err == msg2
    assert rc == 0

def test_run_shell_cmd_bench_fatal():
    from krun.platform import detect_platform
    cmd = "nonsensecommand"
    platform = detect_platform(None, None)
    out, err, rc = run_shell_cmd_bench(cmd, platform, False)
    assert rc != 0
    assert cmd in err
    assert out == ""

def test_check_and_parse_execution_results0001():
    stdout = json.dumps({
        "wallclock_times": [123.4],
        "core_cycle_counts": [[1], [2], [3], [4]],
        "aperf_counts": [[5], [6], [7], [8]],
        "mperf_counts": [[9], [10], [11], [12]],
    })
    stderr = "[iterations_runner.py] iteration 1/1"
    assert check_and_parse_execution_results(stdout, stderr, 0) == json.loads(stdout)


def test_check_and_parse_execution_results0002():
    stdout = json.dumps({
        "wallclock_times": [123.4],
        "core_cycle_counts": [[1], [2], [3], [4]],
        "aperf_counts": [[5], [6], [7], [8]],
        "mperf_counts": [[9], [10], [11], [12]],
    })
    stderr = "[iterations_runner.py] iteration 1/1"
    # Non-zero return code.
    with pytest.raises(ExecutionFailed) as excinfo:
        check_and_parse_execution_results(stdout, stderr, 1)
    expected = """Benchmark returned non-zero or emitted invalid JSON.
return code: 1
stdout:
--------------------------------------------------
%s
--------------------------------------------------

stderr:
--------------------------------------------------
[iterations_runner.py] iteration 1/1
--------------------------------------------------
""" % stdout
    assert excinfo.value.message == expected


def test_check_and_parse_execution_results0003():
    stderr = "[iterations_runner.py] iteration 1/1"
    stdout = "[0.000403["
    # Corrupt Json in STDOUT.
    with pytest.raises(ExecutionFailed) as excinfo:
        check_and_parse_execution_results(stdout, stderr, 0)
    expected = """Benchmark returned non-zero or emitted invalid JSON.\nException string: Expecting , delimiter: line 1 column 10 (char 9)
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


def test_get_session_info0001(mock_platform):
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)
    info = get_session_info(config, mock_platform)

    assert info["n_proc_execs"] == 8
    assert info["n_in_proc_iters"] == 40
    assert info["skipped_keys"] == set()

    expect_non_skipped_keys = set([
        "dummy:Java:default-java",
        "nbody:Java:default-java",
        "dummy:CPython:default-python",
        "nbody:CPython:default-python",
    ])
    assert info["non_skipped_keys"] == expect_non_skipped_keys
    os.unlink(ManifestManager.get_filename(config))


def test_get_session_info0002(mock_platform):
    path = os.path.join(TEST_DIR, "more_complicated.krun")
    config = Config(path)
    info = get_session_info(config, mock_platform)

    # 6 benchmarks, 9 VMs, skipped 3 exact keys, and all 6 CPython keys
    # Then two repetitions (process executions) of all of the above.
    expect_proc_execs = (6 * 9 - 3 - 6) * 2
    assert info["n_proc_execs"] == expect_proc_execs

    # 2000 in-process iterations
    assert info["n_in_proc_iters"] == expect_proc_execs * 2000

    expect_skip_keys = [
        "fasta:JRubyTruffle:default-ruby",
        "richards:HHVM:default-php",
        "spectralnorm:JRubyTruffle:default-ruby",
        "binarytrees:CPython:default-python",
        "richards:CPython:default-python",
        "spectralnorm:CPython:default-python",
        "nbody:CPython:default-python",
        "fasta:CPython:default-python",
        "fannkuch_redux:CPython:default-python",
    ]
    assert info["skipped_keys"] == set(expect_skip_keys)

    expect_non_skipped_keys = [
        'richards:C:default-c',
        'nbody:HHVM:default-php',
        'binarytrees:C:default-c',
        'binarytrees:PyPy:default-python',
        'spectralnorm:Hotspot:default-java',
        'fannkuch_redux:Graal:default-java',
        'nbody:JRubyTruffle:default-ruby',
        'fasta:Graal:default-java',
        'binarytrees:Graal:default-java',
        'fasta:C:default-c',
        'binarytrees:JRubyTruffle:default-ruby',
        'spectralnorm:HHVM:default-php',
        'nbody:PyPy:default-python',
        'fannkuch_redux:C:default-c',
        'fannkuch_redux:JRubyTruffle:default-ruby',
        'fannkuch_redux:Hotspot:default-java',
        'spectralnorm:PyPy:default-python',
        'fasta:PyPy:default-python',
        'binarytrees:Hotspot:default-java',
        'nbody:C:default-c',
        'richards:JRubyTruffle:default-ruby',
        'fasta:V8:default-javascript',
        'nbody:V8:default-javascript',
        'richards:V8:default-javascript',
        'nbody:LuaJIT:default-lua',
        'richards:Hotspot:default-java',
        'fasta:LuaJIT:default-lua',
        'binarytrees:LuaJIT:default-lua',
        'fannkuch_redux:V8:default-javascript',
        'fannkuch_redux:LuaJIT:default-lua',
        'richards:Graal:default-java',
        'binarytrees:V8:default-javascript',
        'spectralnorm:LuaJIT:default-lua',
        'spectralnorm:C:default-c',
        'fannkuch_redux:HHVM:default-php',
        'fannkuch_redux:PyPy:default-python',
        'binarytrees:HHVM:default-php',
        'fasta:HHVM:default-php',
        'spectralnorm:V8:default-javascript',
        'spectralnorm:Graal:default-java',
        'nbody:Graal:default-java',
        'richards:LuaJIT:default-lua',
        'nbody:Hotspot:default-java',
        'richards:PyPy:default-python',
        'fasta:Hotspot:default-java'
    ]
    assert info["non_skipped_keys"] == set(expect_non_skipped_keys)

    # There should be no overlap in the used and skipped keys
    assert info["skipped_keys"].intersection(info["non_skipped_keys"]) == set()
    os.unlink(ManifestManager.get_filename(config))


def test_run_shell_cmd_list0001():
    path = os.path.join(TEST_DIR, "shell-out")
    cmds = [
        "echo 1 > %s" % path,
        "echo 2 >> %s" % path,
        "echo 3 >> %s" % path,
    ]

    run_shell_cmd_list(cmds)

    with open(path) as fh:
        got = fh.read()

    os.unlink(path)
    assert got == "1\n2\n3\n"


def test_run_shell_cmd_list0002(caplog):
    path = os.path.join(TEST_DIR, "shell-out")
    cmds = [
        "echo 1 > %s" % path,
        "/flibblebop 2 >> %s" % path,  # failing command
        "echo 3 >> %s" % path,
    ]

    with pytest.raises(FatalKrunError):
        run_shell_cmd_list(cmds)

    with open(path) as fh:
        got = fh.read()

    os.unlink(path)
    assert got == "1\n"

    expect = "Command failed: '/flibblebop"
    assert expect in caplog.text()


def test_run_shell_cmd_list0003():
    path = os.path.join(TEST_DIR, "shell-out")
    cmds = [
        "echo ${TESTVAR}  > %s" % path,
        "echo ${TESTVAR2} >> %s" % path,
    ]

    run_shell_cmd_list(cmds, extra_env={
        "TESTVAR": "test123", "TESTVAR2": "test456"})

    with open(path) as fh:
        got = fh.read()

    os.unlink(path)
    assert got == "test123\ntest456\n"


def test_run_shell_cmd_list0004(caplog):
    path = os.path.join(TEST_DIR, "shell-out")
    cmds = [
        "echo ${TESTVAR}  > %s" % path,
        "echo ${TESTVAR2} >> %s" % path,
    ]

    with pytest.raises(FatalKrunError):
        run_shell_cmd_list(cmds, extra_env={"HOME": "test123"})

    expect = "Environment HOME is already defined"
    assert expect in caplog.text()


def test_get_git_version0001():
    vers = get_git_version()
    int(vers, 16)
    # should not crash


def test_stash_envlog0001(mock_platform):
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)

    env = "A=1\nB=2\nC=3\n"
    with NamedTemporaryFile(prefix="kruntest-", delete=False) as fh:
        fh.write(env)
        filename = fh.name

    stash_envlog(filename, config, mock_platform, "bench:vm:variant", 1337)
    stashed_logdir = os.path.join(TEST_DIR, "example_envlogs")
    stashed_logfile = os.path.join(stashed_logdir,
                                   "bench__vm__variant__1337.env")
    with open(stashed_logfile) as fh:
        got = fh.read()

    os.unlink(stashed_logfile)
    os.rmdir(stashed_logdir)
    assert got == env


def test_dump_instr_json0001():
    path = os.path.join(TEST_DIR, "example.krun")
    config = Config(path)

    instr_data = {k: ord(k) for k in "abcdef"}
    dump_instr_json("bench:vm:variant", 666, config, instr_data)

    dump_dir = os.path.join(TEST_DIR, "example_instr_data")
    dump_file = os.path.join(dump_dir, "bench__vm__variant__666.json.bz2")
    with BZ2File(dump_file) as fh:
        js = json.load(fh)

    os.unlink(dump_file)
    os.rmdir(dump_dir)

    assert js == instr_data
