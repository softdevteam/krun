from krun.tests.mocks import MockPlatform, MockMailer
from abc import ABCMeta
from krun.platform import detect_platform
import pytest


class BaseKrunTest(object):
    """Abstract class defining common functionality for Krun tests."""

    __metaclass__ = ABCMeta

    @pytest.fixture
    def mock_platform(self):
        return MockPlatform(MockMailer())

    @pytest.fixture
    def platform(self):
        return detect_platform(MockMailer())

