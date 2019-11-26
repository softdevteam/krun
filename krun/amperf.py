#!/usr/bin/env python2.7

import sys
import os
from logging import debug


class AMPerfRatios(object):
    """Per-core {A,M}PERF analysis results"""

    def __init__(self, vals, violations, busy_iters):
        self.vals = vals  # list of ratios
        self.violations = violations  # dict: type_string -> [iter_idxs]
        self.busy_iters = busy_iters  # list of bool

    def ok(self):
        for iters in self.violations.itervalues():
            if len(iters) > 0:
                return False
        return True


sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def check_amperf_ratios(aperfs, mperfs, wc_times, busy_threshold, ratio_bounds):
    results = []  # one AMPerfRatios instance for each core

    for core_idx in xrange(len(aperfs)):
        core_res = check_core_amperf_ratios(core_idx, aperfs[core_idx],
                                            mperfs[core_idx], wc_times,
                                            busy_threshold, ratio_bounds)
        results.append(core_res)
    return results


def check_core_amperf_ratios(core_idx, aperfs, mperfs, wc_times, busy_threshold,
                             ratio_bounds):
    assert len(aperfs) == len(mperfs) == len(wc_times)
    ratios = []
    busy_iters = []
    violations = {
        "throttle": [],
        "turbo": [],
    }

    itr = zip(xrange(len(aperfs)), aperfs, mperfs, wc_times)
    for iter_idx, aval, mval, wctval in itr:
        # normalise the counts to per-second readings
        norm_aval = float(aval) / wctval
        norm_mval = float(mval) / wctval
        ratio = norm_aval / norm_mval
        ratios.append(ratio)

        if norm_aval > busy_threshold:
            # Busy core
            busy_iters.append(True)
            if ratio < ratio_bounds[0]:
                violations["throttle"].append(iter_idx)
            elif ratio > ratio_bounds[1]:
                violations["turbo"].append(iter_idx)
        else:
            busy_iters.append(False)
    return AMPerfRatios(ratios, violations, busy_iters)
