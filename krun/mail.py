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

from email.mime.text import MIMEText
import socket
import textwrap
import logging
from subprocess import Popen, PIPE


FROM_USER = "noreply"
SMTP_HOST = "localhost"
WRAP_THRESHOLD = 72

QUOTA_THRESHOLD_TEMPLATE = (
    "Note: krun is configured to send no more than %d mails per-run. "
    "This is the last email krun will send for this run. Please check "
    "the log file on the benchmark system for subsequent errors.")

SENDMAIL = "/usr/sbin/sendmail"


class Mailer(object):
    def __init__(self, recipients=None, max_mails=5):
        if recipients is not None:
            self.recipients = recipients
        else:
            self.recipients = []
        self.hostname = socket.gethostname()
        self.short_hostname = self.hostname.split(".")[0]

        # After sending the maximum number of emails, we stop sending more so
        # as not to spam. Some emails however, you will always want to send.
        # For these use send(..., bypass_limiter=True).
        self.max_mails = max_mails

    def set_recipients(self, recipients):
        self.recipients = recipients

    def _wrap_para(self, txt):
        return "\n".join(textwrap.wrap(txt, WRAP_THRESHOLD))

    def send(self, append_subject, inner_body, bypass_limiter=False,
             manifest=None):
        if manifest is not None:
            num_mails_sent = manifest.num_mails_sent
        else:
            # It's OK to call this without a manifest (e.g. outside the
            # scheduler loop, where there is no manifest to speak of), but
            # without a manifest we can't know how many emails have been sent.
            # So, the only time this is OK is if we are skipping the limiter
            # anyway.
            assert bypass_limiter  # Krun can't know how many mails were sent
            num_mails_sent = 0

        if not self.recipients:
            # Don't bother mailing if there are no recipients
            return

        if bypass_limiter or num_mails_sent < self.max_mails:
            body = "Message from krun running on %s:\n\n" % self.hostname
            body += inner_body + "\n"

            if not bypass_limiter and num_mails_sent == self.max_mails - 1:
                body += "\n\n%s" % self._wrap_para(
                    QUOTA_THRESHOLD_TEMPLATE % self.max_mails)
                logging.warn("Mail quota reached.")

            msg = MIMEText(body)  # text/plain
            msg['Subject'] = '[krun:%s] %s' % \
                (self.short_hostname, append_subject)
            msg['From'] = "%s@%s" % (FROM_USER, self.hostname)
            msg['To'] = ", ".join(self.recipients)
            self._sendmail(msg)

            if not bypass_limiter:
                manifest.update_num_mails_sent()
        else:
            pass  # as we have already sent our quota of mails

    def _sendmail(self, msg):
        logging.debug("Sending email to '%s' subject line '%s'" %
                      (msg['To'], msg['Subject']))

        pipe = Popen([SENDMAIL, "-t", "-oi"], stdin=PIPE)
        pipe.communicate(msg.as_string())

        rc = pipe.returncode
        if rc != 0:
            logging.warning("Sendmail process returned %d" % rc)
