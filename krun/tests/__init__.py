from krun.tests.mocks import MockPlatform, MockMailer
from abc import ABCMeta
from krun.platform import detect_platform
import pytest


def subst_env_arg(lst, var):
    """E.g. replace list elements like 'MYVAR=something' with 'MYVAR='"""

    find = var + "="
    new = []
    for i in lst:
        if i.startswith(find):
            i = find
        new.append(i)
    return new


class BaseKrunTest(object):
    """Abstract class defining common functionality for Krun tests."""

    __metaclass__ = ABCMeta

    @pytest.fixture
    def mock_platform(self):
        return MockPlatform(MockMailer())

    @pytest.fixture
    def platform(self):
        return detect_platform(MockMailer())

