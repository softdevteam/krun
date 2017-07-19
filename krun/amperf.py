#!/usr/bin/env python2.7
#
# Copyright (c) 2017 King's College London
# created by the Software Development Team <http://soft-dev.org/>
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or
# data (collectively the "Software"), free of charge and under any and all
# copyright rights in the Software, and any and all patent rights owned or
# freely licensable by each licensor hereunder covering either (i) the
# unmodified Software as contributed to or provided by such licensor, or (ii)
# the Larger Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
# one is included with the Software (each a "Larger Work" to which the Software
# is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright
# notice and either this complete permission notice or at a minimum a reference
# to the UPL must be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
