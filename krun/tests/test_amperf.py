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

from krun.amperf import check_core_amperf_ratios


GHZ_3_6 = 3.6 * 1024 * 1024 * 1024  # 3.6 GHz


def test_ok_ratios0001():
    """Check ratios which are all 1.0 are OK"""

    busy_threshold = GHZ_3_6 / 1000
    ratio_bounds = 0.999, 1.001

    aperfs = mperfs = [GHZ_3_6 for x in xrange(2000)]
    wcts = [1.0 for x in xrange(2000)]

    ratios = check_core_amperf_ratios(
        0, aperfs, mperfs, wcts, busy_threshold, ratio_bounds)

    assert all([r == 1.0 for r in ratios.vals])
    assert ratios.ok()


def test_ok_ratios0002():
    """Check normalisation by time is working"""

    busy_threshold = GHZ_3_6 / 1000
    ratio_bounds = 0.999, 1.001

    aperfs = mperfs = [GHZ_3_6 / 2.0 for x in xrange(2000)]
    wcts = [0.5 for x in xrange(2000)]

    ratios = check_core_amperf_ratios(
        0, aperfs, mperfs, wcts, busy_threshold, ratio_bounds)

    assert all([r == 1.0 for r in ratios.vals])
    assert ratios.ok()


def test_bad_ratios0001():
    """Check throttle problems are detected"""

    busy_threshold = GHZ_3_6 / 1000
    ratio_bounds = 0.9, 1.1

    aperfs = [GHZ_3_6 for x in xrange(2000)]
    mperfs = aperfs[:]
    wcts = [1.0 for x in xrange(2000)]
    aperfs[501] = GHZ_3_6 / 4

    ratios = check_core_amperf_ratios(
        0, aperfs, mperfs, wcts, busy_threshold, ratio_bounds)

    assert not all([r == 1.0 for r in ratios.vals])
    assert not ratios.ok()
    assert ratios.violations["throttle"] == [501]


def test_bad_ratios0002():
    """Check turbo problems are detected"""

    busy_threshold = GHZ_3_6 / 1000
    ratio_bounds = 0.9, 1.1

    aperfs = [GHZ_3_6 for x in xrange(2000)]
    mperfs = aperfs[:]
    wcts = [1.0 for x in xrange(2000)]
    aperfs[666] = GHZ_3_6 * 1.25

    ratios= check_core_amperf_ratios(
        0, aperfs, mperfs, wcts, busy_threshold, ratio_bounds)

    assert not all([r == 1.0 for r in ratios.vals])
    assert not ratios.ok()
    assert ratios.violations["turbo"] == [666]


def test_bad_ratios0003():
    """Check a mix of problems are detected"""

    busy_threshold = GHZ_3_6 / 1000
    ratio_bounds = 0.9, 1.1

    aperfs = [GHZ_3_6 for x in xrange(2000)]
    mperfs = aperfs[:]
    wcts = [1.0 for x in xrange(2000)]

    # Mixed bag of problems here
    aperfs[14] = GHZ_3_6 * 0.77    # throttle
    mperfs[307] = GHZ_3_6 * 0.8    # turbo
    aperfs[788] = GHZ_3_6 * 1.15   # turbo
    aperfs[1027] = GHZ_3_6 * 0.62  # throttle
    mperfs[1027] = GHZ_3_6 * 0.84  # ^^^^^^^^

    ratios = check_core_amperf_ratios(
        0, aperfs, mperfs, wcts, busy_threshold, ratio_bounds)

    assert not all([r == 1.0 for r in ratios.vals])
    assert not ratios.ok()
    assert ratios.violations["turbo"] == [307, 788]
    assert ratios.violations["throttle"] == [14, 1027]
