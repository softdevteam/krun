import sys
from subprocess import Popen, PIPE
from logging import error

def should_skip(config, this_key):
    skips = config["SKIP"]

    for skip_key in skips:
        skip_elems = skip_key.split(":")
        this_elems = this_key.split(":")

        # should be triples of: bench * vm * variant
        assert len(skip_elems) == 3 and len(this_elems) == 3

        for i in range(3):
            if skip_elems[i] == "*":
                this_elems[i] = "*"

        if skip_elems == this_elems:
            return True # skip

    return False


def read_config(path):
    assert path.endswith(".krun")
    dct = {}
    try:
        execfile(path, dct)
    except:
        fatal("error importing config file")

    return dct


def output_name(config_path):
    assert config_path.endswith(".krun")
    return config_path[:-5] + "_results.json"


def fatal(msg):
    error(msg)
    sys.exit(1)


def collect_cmd_output(cmd):
    p = Popen(cmd, shell=True, stdout=PIPE)
    stdout, stderr = p.communicate()
    rc = p.wait()
    assert rc == 0
    return stdout.strip()
