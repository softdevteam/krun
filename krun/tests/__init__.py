from krun.tests.mocks import MockPlatform, MockMailer
from abc import ABCMeta
import pytest


class BaseKrunTest(object):
    """Abstract class defining common functionality for Krun tests."""

    __metaclass__ = ABCMeta

    @pytest.fixture
    def mock_platform(self):
        return MockPlatform(MockMailer())
