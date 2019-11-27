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
