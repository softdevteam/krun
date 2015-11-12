from krun.results import Results

import os


def test_read_results_from_disk():
    results = Results(results_file='krun/tests/quick_results.json.bz2')
    expected = {u'nbody:CPython:default-python': [[0.022256]],
                u'dummy:CPython:default-python': [[1.005115]],
                u'nbody:Java:default-java': [[26.002632]],
                u'dummy:Java:default-java': [[1.000941]]}
    with open('krun/tests/quick.krun', 'rb') as config_fp:
        config = config_fp.read()
    assert results.config == config
    assert results.audit['uname'] == u'Linux'
    assert results.audit['debian_version'] == u'jessie/sid'
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
    out_file = "krun/tests/example_results.json.bz2"
    results0 = Results()
    results0.audit = "example audit (py.test)"
    results0.starting_temperatures = [4355, 9879]
    results0.data = {"dummy:Java:default-java": [[1.000726]]}
    results0.etas = {"dummy:Java:default-java": [1.1]}
    results0.reboots = 5
    results0.error_flag = False
    with open("krun/tests/example.krun", "r") as fp:
        results0.config = fp.read()
    results0.write_to_file(out_file)
    results1 = Results(results_file=out_file)
    assert results0 == results1
    # Clean-up generated file.
    os.unlink(out_file)
