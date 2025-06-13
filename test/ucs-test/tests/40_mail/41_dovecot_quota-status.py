#!/usr/share/ucs-test/runner python3
## desc: Test Dovecots quota-status service for Postfix
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools
## bugs: [38727]

# * quota-service for Postfix: new mails should be rejected during SMTP dialogue if user is over quota (until 110%
#   is allowed)
#   a) user under quota should receive email
#   b) for a user over quota, Postfix should reject the mail (not bounce)

import smtplib
import socket
import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import mail_delivered, send_mail


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            quota01 = 2
            domain = ucr.get('domainname')
            pw = 'univention'
            mail = '%s@%s' % (uts.random_name(), domain)
            _userdn, _username = udm.create_user(
                password=pw,
                set={
                    "mailHomeServer": '%s.%s' % (ucr.get("hostname"), domain),
                    "mailPrimaryAddress": mail,
                    "mailUserQuota": str(quota01),
                })

            #
            # send email with a size of 70% of quota, should be accepted
            #
            msg1 = "Lorem ipsum dolor sit amet, consetetur sadipscing " * quota01 * 21000  # go a tiny bit over quota
            print(f'Sending mail with body size {len(msg1) / 1024!r} KB.')
            send_mail(
                recipients=[mail],
                subject="41_dovecot_quota-status 1",
                msg=msg1,
                server=socket.gethostname(),
                debuglevel=0)
            print('OK: Mail was received.')
            time.sleep(10)
            subprocess.call(["/usr/bin/doveadm", "quota", "recalc", "-u", mail])
            print(f'Output of "doveadm quota get -u {mail}":')
            subprocess.call(["/usr/bin/doveadm", "quota", "get", "-u", mail])

            if not mail_delivered("Subject: 41_dovecot_quota-status 1", mail_address=mail):
                utils.fail(
                    "Fail: under quota message not delivered missing (quota was"
                    " set to %d MB, len(message body): %d KB)." % (quota01, len(msg1) / 1024),
                )

            #
            # send email with a size of 50% of quota, should be rejected during SMTP dialogue
            #
            msg2 = "Lorem ipsum dolor sit amet, consetetur sadipscing "
            rejected = False
            try:
                send_mail(
                    recipients=[mail],
                    subject="41_dovecot_quota-status 2",
                    msg=msg2,
                    server=socket.gethostname(),
                    debuglevel=0)
                print('FAIL: Mail was not rejected.')
            except smtplib.SMTPRecipientsRefused:
                rejected = True
                print('OK: Mail was rejected.')
            subprocess.call(["/usr/bin/doveadm", "quota", "recalc", "-u", mail])
            print(f'Output of "doveadm quota get -u {mail}":')
            subprocess.call(["/usr/bin/doveadm", "quota", "get", "-u", mail])
            if not rejected or mail_delivered("Subject: 41_dovecot_quota-status 2", mail_address=mail):
                utils.fail(
                    "Fail: over quota message was delivered (quota was set to %d MB, len(message body 1): "
                    "%d KB, len(message body 2): %d KB). " % (quota01, len(msg1) / 1024, len(msg2) / 1024),
                )


if __name__ == '__main__':
    main()
