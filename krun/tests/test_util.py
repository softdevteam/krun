from krun import LOGFILE_FILENAME_TIME_FORMAT
from krun.util import (should_skip, format_raw_exec_results, output_name,
                       log_name, fatal, read_config, run_shell_cmd)

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
