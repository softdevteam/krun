#!/usr/bin/env python2.7
# A dummy external script, demonstrating how the ExternalSuiteVMDef works.
#
# This script is called once for each process execution.

import sys
import json

_, benchmark, iters, param, instr = sys.argv
iters = int(iters)

# <INSERT INVOCATION OF PROCESS EXECUTION HERE>

# Then emit your results to stdout in the following format:
js = {
    "wallclock_times": list(range(iters)),  # dummy results.
    # ExternalSuiteVMDef doesn't support the following fields.
    "core_cycle_counts": [],
    "aperf_counts": [],
    "mperf_counts": [],
}

sys.stdout.write("%s\n" % json.dumps(js))
