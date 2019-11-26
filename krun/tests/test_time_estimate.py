from krun.time_estimate import TimeEstimateFormatter
from krun import UNKNOWN_TIME_DELTA, UNKNOWN_ABS_TIME

import datetime
import pytest

PHONY_TIME = datetime.datetime(1970, 1, 1, 12, 0, 0, 0)

@pytest.fixture
def patch_datetime_now(monkeypatch):
    """http://stackoverflow.com/questions/20503373
    Code by @sashk
    """
    class datetime_patch:
        @classmethod
        def now(cls):
            return PHONY_TIME
    monkeypatch.setattr(datetime, 'datetime', datetime_patch)


def test_time_estimate_none(patch_datetime_now):
    tef = TimeEstimateFormatter(None)
    assert tef.start_str == '1970-01-01 12:00:00'
    assert tef.finish_str == UNKNOWN_ABS_TIME
    assert tef.delta_str == UNKNOWN_TIME_DELTA


def test_time_estimate(patch_datetime_now):
    tef = TimeEstimateFormatter(100)
    assert tef.start_str == '1970-01-01 12:00:00'
    assert tef.finish_str == '1970-01-01 12:01:40'
    assert tef.delta_str == '0:01:40'
