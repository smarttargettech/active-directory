#!/usr/share/ucs-test/runner python3
## desc: Mails to unknown users are rejected
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]
import smtplib
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import send_mail


def check_sending_mail(username, password, recipient_email, should_be_accepted):
    token = str(time.time())
    try:
        ret_code = send_mail(recipients=recipient_email, msg=token, tls=True, username=username, password=password)
        if bool(ret_code) == should_be_accepted:
            utils.fail('Sending should_be_accepted = %r, but return code = %r\n {} means there are no refused recipient' % (should_be_accepted, ret_code))
    except smtplib.SMTPRecipientsRefused as exc:
        if should_be_accepted:
            utils.fail('Mail sent failed with exception: %s' % exc)


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr, udm_test.UCSTestUDM() as udm:
        maildomain = '%s.%s' % (uts.random_name(), uts.random_name())
        udm.create_object(
            'mail/domain',
            set={
                'name': maildomain,
            },
            position="cn=domain,cn=mail,{}".format(ucr.get("ldap/base")),
        )

        password = 'univention'
        recipient_email = '%s@%s' % (uts.random_name(), maildomain)
        unknown_email = '%s@%s' % (uts.random_name(), maildomain)
        udm.create_user(
            set={
                'password': password,
                'mailHomeServer': '%s.%s' % (ucr.get('hostname'), maildomain),
                'mailPrimaryAddress': recipient_email,
            },
        )

        check_sending_mail(recipient_email, password, recipient_email, True)
        check_sending_mail(recipient_email, password, unknown_email, False)


if __name__ == '__main__':
    main()
