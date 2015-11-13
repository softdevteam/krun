from krun.config import Config
from krun.results import Results
from krun.tests.mocks import MockPlatform, MockMailer

import os


def test_eq():
    results = Results(None, None,
                      results_file="krun/tests/quick_results.json.bz2")
    assert results == results
    assert not results == None
    assert not results == Results(Config("krun/tests/example.krun"),
                                  MockPlatform(MockMailer()))


def test_dump_config():
    """Simulates krun.py --dump-config RESULTS_FILE.json.bz2
    """
    results = Results(None, None,
                      results_file="krun/tests/quick_results.json.bz2")
    with open("krun/tests/quick.krun") as fp:
        config = fp.read()
        assert config == results.config.text


def test_read_results_from_disk():
    config = Config("krun/tests/quick.krun")
    results = Results(None, None,
                      results_file="krun/tests/quick_results.json.bz2")
    expected = {u'nbody:CPython:default-python': [[0.022256]],
                u'dummy:CPython:default-python': [[1.005115]],
                u'nbody:Java:default-java': [[26.002632]],
                u'dummy:Java:default-java': [[1.000941]]}
    assert results.config == config
    assert results.audit[u'uname'] == u'Linux'
    assert results.audit[u'debian_version'] == u'jessie/sid'
    assert results.data == expected
    assert results.starting_temperatures == [4355, 9879]
    assert results.eta_estimates == \
        {
            u'nbody:CPython:default-python': [0.022256],
            u'dummy:CPython:default-python': [1.005115],
            u'nbody:Java:default-java': [26.002632],
            u'dummy:Java:default-java': [1.000941]
        }


def test_write_results_to_disk():
    config = Config("krun/tests/example.krun")
    out_file = "krun/tests/example_results.json.bz2"
    results0 = Results(config, MockPlatform(MockMailer()))
    results0.audit = dict()
    results0.starting_temperatures = [4355, 9879]
    results0.data = {u"dummy:Java:default-java": [[1.000726]]}
    results0.eta_estimates = {u"dummy:Java:default-java": [1.1]}
    results0.reboots = 5
    results0.error_flag = False
    results0.write_to_file()
    results1 = Results(config, None, results_file=out_file)
    assert results0 == results1
    # Clean-up generated file.
    os.unlink(out_file)
