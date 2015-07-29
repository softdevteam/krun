from email.mime.text import MIMEText
import socket
import textwrap
import logging
from subprocess import Popen, PIPE


FROM_USER = "noreply"
SMTP_HOST = "localhost"
WRAP_THRESHOLD = 72
RULE = WRAP_THRESHOLD * "#"

QUOTA_THRESHOLD_TEMPLATE = (
    "Note: krun is configured to send no more than %d mails per-run. "
    "This is the last email krun will send for this run. Please check "
    "the log file on the benchmark system for subsequent errors.")

SENDMAIL = "/usr/sbin/sendmail"


class Mailer(object):
    def __init__(self, recipients, max_mails):
        self.recipients = recipients
        self.fqdn = socket.getfqdn()

        # After sending max_mails emails, we stop sending more so as
        # not to spam. Some emails however, you will always want to send.
        # For these use send(..., bypass_limiter=True).
        self.max_mails = max_mails
        self.n_mails_sent = 0

    def set_recipients(self, recipients):
        self.recipients = recipients

    def _wrap_para(self, txt):
        return "\n".join(textwrap.wrap(txt, WRAP_THRESHOLD))

    def send(self, append_subject, inner_body, bypass_limiter=False):
        if not self.recipients:
            # Don't bother mailing if there are no recipients
            return

        if self.n_mails_sent < self.max_mails or bypass_limiter:
            body = "Message from krun running on %s:\n\n" % self.fqdn
            body += RULE + "\n"
            body += inner_body + "\n"
            body += RULE + "\n"

            if self.n_mails_sent == self.max_mails - 1 and not bypass_limiter:
                body += "\n\n%s" % self._wrap_para(
                    QUOTA_THRESHOLD_TEMPLATE % self.max_mails)
                logging.warn("Mail quota reached.")

            msg = MIMEText(body)  # text/plain
            msg['Subject'] = '[krun] ' + append_subject
            msg['From'] = "%s@%s" % (FROM_USER, self.fqdn)
            msg['To'] = ", ".join(self.recipients)

            pipe = Popen([SENDMAIL, "-t", "-oi"], stdin=PIPE)
            pipe.communicate(msg.as_string())

            if pipe.returncode != 0:
                logging.error("mailing failed!")

            if not bypass_limiter:
                self.n_mails_sent += 1
        else:
            pass  # as we have already sent our quota of mails
