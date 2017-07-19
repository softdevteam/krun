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

"""
Draw plots to help you decide a suitable APERF/MPERF tolerance.

usages:
   calibrate_amperf_tolerance.py analyse <result-file> <aperf-estimate>")
   calibrate_amperf_tolerance.py plot-hist <amstat-file>")
   calibrate_amperf_tolerance.py plot-dropoff <amstat-file>")

First use "analyse" mode to analyse the results, then use one of the "plot-*"
modes to generate plots from the analysed data.
"""

import json
import sys
import os
import bz2
from collections import OrderedDict

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from krun.amperf import check_amperf_ratios


TOLERANCES = [(i + 1) * 0.0005 for i in xrange(80)]


def analyse_amperf(jsn, busy_thresh, output_filename):
    # Each of these maps a tolerance to a count
    bad_pexecs = OrderedDict()
    bad_iters = OrderedDict()
    for tol in TOLERANCES:
        # The totals are the same on eacch iteration, so it's OK to use the
        # value from the final iteration
        total_pexecs, total_iters, bad_pexecs[tol], bad_iters[tol] = \
            _analyse_amperf(jsn, busy_thresh, tol)

    bad_pexecs_xs, bad_pexecs_ys = zip(*bad_pexecs.iteritems())
    bad_iters_xs, bad_iters_ys = zip(*bad_iters.iteritems())

    # JSON can't deal with tuples
    bad_pexecs_xs, bad_pexecs_ys = list(bad_pexecs_xs), list(bad_pexecs_ys)
    bad_iters_xs, bad_iters_ys = list(bad_iters_xs), list(bad_iters_ys)

    ratios = _collect_busy_ratios(jsn, busy_thresh)

    dct = {
        "bad_pexecs": [bad_pexecs_xs, bad_pexecs_ys],
        "bad_iters": [bad_iters_xs, bad_iters_ys],
        "total_pexecs": total_pexecs,
        "total_iters": total_iters,
        "ratios": ratios,
    }
    print("\ndumping to %s" % output_filename)
    with open(output_filename, "w") as fh:
        json.dump(dct, fh, indent=2)


def _analyse_amperf(jsn, busy_thresh, tol):
    """Returns the number of bad process executions and in-process
    iterations"""

    num_bad_pexecs = 0
    num_bad_iters = 0
    total_pexecs = 0
    total_iters = 0

    sys.stdout.write("\ntolerance: %8.5f: " % tol)
    bounds = 1.0 - tol, 1.0 + tol
    for bench in jsn["wallclock_times"]:
        sys.stdout.write(".")
        sys.stdout.flush()
        for pexec_idx in xrange(len(jsn["wallclock_times"][bench])):
            total_pexecs += 1
            aperfs = jsn["aperf_counts"][bench][pexec_idx]
            mperfs = jsn["mperf_counts"][bench][pexec_idx]
            wc_times = jsn["wallclock_times"][bench][pexec_idx]
            total_iters += len(wc_times)
            res = check_amperf_ratios(aperfs, mperfs, wc_times, busy_thresh,
                                      bounds)
            bad_iters = set()
            for core in res:
                # iterate different types of badness
                for idxs in core.violations.itervalues():
                    bad_iters.update(idxs)
            if len(bad_iters) > 0:
                num_bad_pexecs += 1
            num_bad_iters += len(bad_iters)
    return total_pexecs, total_iters, num_bad_pexecs, num_bad_iters


def _collect_busy_ratios(jsn, busy_thresh):
    ratios = []
    for bench in jsn["wallclock_times"]:
        bounds = 0, 2  # irrelevant for this mode really.
        for pexec_idx in xrange(len(jsn["wallclock_times"][bench])):
            aperfs = jsn["aperf_counts"][bench][pexec_idx]
            mperfs = jsn["mperf_counts"][bench][pexec_idx]
            wc_times = jsn["wallclock_times"][bench][pexec_idx]
            res = check_amperf_ratios(aperfs, mperfs, wc_times, busy_thresh,
                                      bounds)
            for core_res in res:
                for busy, ratio in zip(core_res.busy_iters, core_res.vals):
                    if busy:
                        ratios.append(ratio)
    return ratios


def plot_hist(jsn, output_filename):
    ratios = jsn["ratios"]
    n_bins = 1000

    f, ax = plt.subplots(1, 1, sharey=False, figsize=(20, 10))

    ax.hist(ratios, n_bins, facecolor="red", alpha=0.75)
    ax.set_xlabel("Ratio")
    ax.set_ylabel("Count")
    ax.set_title("Probability Distribution of A/MPERF ratios")
    ax.grid(True)

    print("Plotting to %s" % output_filename)
    plt.savefig(output_filename)


def plot_dropoff(jsn, output_filename):
    total_iters, total_pexecs = \
        int(jsn["total_iters"]), int(jsn["total_pexecs"])
    bad_pexecs_xs, bad_pexecs_ys = jsn["bad_pexecs"]
    bad_iters_xs, bad_iters_ys = jsn["bad_iters"]

    # Convert from good to bad (inverse)
    good_pexecs_ys = [total_pexecs - y for y in bad_pexecs_ys]
    good_iters_ys = [total_iters - y for y in bad_iters_ys]
    good_pexecs_xs = bad_pexecs_xs  # These are the same, just a renaming
    good_iters_xs = bad_iters_xs

    # Convert Y-axes to percentages
    good_pexecs_ys = [float(x) / total_pexecs * 100 for x in good_pexecs_ys]
    good_iters_ys = [float(x) / total_iters * 100 for x in good_iters_ys]

    f, (ax1, ax2) = plt.subplots(1, 2, sharey=False, figsize=(20, 10))

    ax1.plot(good_pexecs_xs, good_pexecs_ys)
    ax1.set_title("Good Process Executions")
    ax1.set_xlabel("Tolerance")
    ax1.set_ylabel("% pexecs")
    ax1.set_ylim([0, 102])
    ax1.grid(color="r", linestyle="--")
    ax1.set_yticks([(x + 1) * 5 for x in xrange(20)])

    ax2.plot(good_iters_xs, good_iters_ys)
    ax2.set_title("Good In-Process Iterations")
    ax2.set_xlabel("Tolerance")
    ax2.set_ylabel("% iters")
    ax2.set_ylim([0, 102])
    ax2.grid(color="r", linestyle="--")
    ax2.set_yticks([(x + 1) * 5 for x in xrange(20)])

    print("Plotting to %s" % output_filename)
    plt.savefig(output_filename)


def load_json(filename, bzip=True):
    if bzip:
        fn = bz2.BZ2File
    else:
        fn = open

    with fn(filename) as fh:
        jsn = json.load(fh)
    return jsn


def usage():
    print(__doc__)
    sys.exit(1)

if __name__ == "__main__":
    try:
        mode = sys.argv[1]
        filename = sys.argv[2]
    except IndexError:
        usage()

    if mode.startswith("plot"):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

    dot_index = filename.index(".")
    if mode == "compute":
        try:
            busy_thresh = int(sys.argv[3])
        except IndexError:
            usage()
        jsn = load_json(filename)
        output_filename = "%s-amstats-%s.json" % (filename[:dot_index],
                                                  busy_thresh)
        analyse_amperf(jsn, busy_thresh, output_filename)
    elif mode == "plot-dropoff":
        jsn = load_json(filename, bzip=False)
        output_filename = "%s-dropoff.pdf" % filename[:dot_index]
        plot_dropoff(jsn, output_filename)
    elif mode == "plot-hist":
        jsn = load_json(filename, bzip=False)
        output_filename = "%s-hist.pdf" % filename[:dot_index]
        plot_hist(jsn, output_filename)
    else:
        print("bad usage")
