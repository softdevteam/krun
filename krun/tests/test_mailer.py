import os
import pytest
from krun.tests.mocks import mock_mailer, mock_platform
from krun.scheduler import ManifestManager
from krun.tests import TEST_DIR
from krun.config import Config
from contextlib import contextmanager


@pytest.yield_fixture
def example_manifest(mock_platform):
    # setup
    config = Config(os.path.join(TEST_DIR, "example.krun"))
    manifest = ManifestManager(config, mock_platform, new_file=True)

    yield manifest

    # teardown
    if os.path.exists(manifest.path):
        os.unlink(manifest.path)


def test_mailer0001(mock_mailer, example_manifest):
    mock_mailer.max_mails = 5
    mock_mailer.set_recipients(["noone@localhost"])

    assert example_manifest.num_mails_sent == 0
    mock_mailer.send("subject1", "body1", manifest=example_manifest)
    assert example_manifest.num_mails_sent == 1

    example_manifest._parse()
    assert example_manifest.num_mails_sent == 1

    assert len(mock_mailer.sent) == 1
    msg = mock_mailer.sent[0]
    assert msg["subject"] == "[krun:tests] subject1"
    assert msg["to"] == "noone@localhost"
    expect_body = "Message from krun running on tests.suite:\n\nbody1\n"
    assert msg.get_payload() == expect_body


def test_mailer0002(mock_mailer, example_manifest):
    mock_mailer.max_mails = 5
    mock_mailer.set_recipients(["noone@localhost", "ghandi@localhost",
                                "rasputin@localhost"])

    assert example_manifest.num_mails_sent == 0
    subject = "subject longer, much longer, blah, wibble, noodles"
    mock_mailer.send(subject, "body1\nbody2\nbody3", manifest=example_manifest)
    assert example_manifest.num_mails_sent == 1

    example_manifest._parse()
    assert example_manifest.num_mails_sent == 1

    assert len(mock_mailer.sent) == 1
    msg = mock_mailer.sent[0]
    assert msg["subject"] == "[krun:tests] %s" % subject

    assert msg["to"] == "noone@localhost, ghandi@localhost, rasputin@localhost"
    expect_body = "Message from krun running on tests.suite:\n" \
        "\nbody1\nbody2\nbody3\n"
    assert msg.get_payload() == expect_body


def test_mailer0003(mock_mailer, example_manifest):
    """Check message limit works"""
    mock_mailer.max_mails = 3
    mock_mailer.set_recipients(["noone@localhost"])

    assert example_manifest.num_mails_sent == 0
    for i in xrange(10):  # too many emails
        mock_mailer.send("subject%s" % i, "body%s" % i, manifest=example_manifest)

    assert example_manifest.num_mails_sent == 3
    msgs = mock_mailer.sent
    assert len(msgs) == 3
    for i in xrange(3):
        assert msgs[i]["subject"].endswith("subject%s" % i)

    # It should however, be possible to send more mail by bypassing the limit
    mock_mailer.send("subject", "body", bypass_limiter=True)
    assert len(msgs) == 4


def test_mailer0004(mock_mailer):
    """Check mailing with no manifest works as expected"""

    mock_mailer.max_mails = 3
    mock_mailer.set_recipients(["noone@localhost"])

    with pytest.raises(AssertionError):
        mock_mailer.send("subject", "body") # No manifest

    assert len(mock_mailer.sent) == 0
    mock_mailer.send("subject", "body", bypass_limiter=True)  # no raise
    assert len(mock_mailer.sent) == 1
