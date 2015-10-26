from krun import LOGFILE_FILENAME_TIME_FORMAT
from krun.util import (should_skip, format_raw_exec_results, output_name,
                       log_name, fatal, read_config, run_shell_cmd,
                       dump_results, check_and_parse_execution_results,
                       audits_same_platform, ExecutionFailed)

import bz2
import json
import os
import pytest
import time

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

def test_output_name():
    assert output_name(".krun") == "_results.json.bz2"
    assert output_name("example.krun") == "example_results.json.bz2"

def test_log_name():
    tstamp = time.strftime(LOGFILE_FILENAME_TIME_FORMAT)
    assert log_name("example.krun") == "example" + "_" + tstamp + ".log"
    assert log_name(".krun") == "_" + tstamp + ".log"

def test_fatal(capsys):
    msg = "example text"
    with pytest.raises(SystemExit):
        fatal(msg)
    out, err = capsys.readouterr()
    assert out == ""
    assert err == "ERROR:root:" + msg + "\n"

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

def test_dump_results():
    config_file = 'krun/tests/example.krun'
    audit = 'example audit (py.test)'
    out_file = output_name(config_file)
    all_results = {'dummy:Java:default-java': [[1.000726]]}
    dump_results(config_file, out_file, all_results, audit)
    with open(config_file, 'r') as config_fp:
        config = config_fp.read()
        with bz2.BZ2File(out_file, 'rb') as input_file:
            dumped_results = json.loads(input_file.read())
            assert dumped_results['audit'] == audit
            assert dumped_results['config'] == config
            assert dumped_results['data'] == all_results
        os.unlink(out_file)  # Clean-up generated file.

def test_check_and_parse_execution_results():
    stdout = "[0.000403]"
    stderr = "[iterations_runner.py] iteration 1/1"
    rc = 1
    assert check_and_parse_execution_results(stdout, stderr, 0) == json.loads(stdout)
    with pytest.raises(ExecutionFailed) as excinfo:
        check_and_parse_execution_results(stdout, stderr, rc)
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

def test_audits_same_platform():
    audit0 = dict([("cpuinfo", u"processor\t: 0\nvendor_id\t: GenuineIntel"),
                   ("uname", u"Linux"),
                   ("debian_version", u"jessie/sid"),
                   ("packages", u"1:1.2.8.dfsg-2ubuntu1"),
                   ("dmesg", u"")])
    audit1 = dict([("cpuinfo", u"processor\t: 0\nvendor_id\t: GenuineIntel"),
                   ("uname", u"Linux"),
                   ("debian_version", u"jessie/stretch"),
                   ("packages", u"1:1.2.8.dfsg-2ubuntu1"),
                   ("dmesg", u"")])
    assert audits_same_platform(audit0, audit0)
    assert audits_same_platform(audit1, audit1)
    assert not audits_same_platform([], [])
    assert not audits_same_platform(audit0, audit1)
    assert not audits_same_platform(audit1, audit0)
