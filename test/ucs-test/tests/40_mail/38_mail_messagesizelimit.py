#!/usr/share/ucs-test/runner python3
## desc: Test mail/messagesizelimit
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]
import smtplib
import tempfile
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import restart_postfix, send_mail


def check_sending_mail(recipient, attachments, username, password, should_be_accepted):
    token = str(time.time())
    try:
        send_mail(
            recipients=recipient,
            attachments=attachments,
            msg=token,
            tls=True,
            username=username,
            password=password,
        )
    except smtplib.SMTPSenderRefused as ex:
        if should_be_accepted:
            utils.fail('Mail sent failed with exception: %s' % ex)


def main():
    cmd = ['/etc/init.d/postfix', 'restart']
    with utils.AutoCallCommand(exit_cmd=cmd, stderr=open('/dev/null', 'w')):
        with ucr_test.UCSTestConfigRegistry() as ucr:
            with udm_test.UCSTestUDM() as udm:
                limit = 8192  # Byte
                handler_set(['mail/messagesizelimit=%r' % limit])
                restart_postfix()
                domain = ucr.get('domainname')
                password = 'univention'
                username = uts.random_name()
                mail = '%s@%s' % (username, domain)
                _user_dn, username = udm.create_user(
                    username=username,
                    set={
                        'password': password,
                        'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                        'mailPrimaryAddress': mail,
                    },
                )

                # Testing exceeding the messagesizelimit
                with tempfile.NamedTemporaryFile() as h:
                    h.truncate(limit * 2)
                    check_sending_mail(mail, [h.name], mail, password, False)

                # Testing being within the messagesizelimit
                with tempfile.NamedTemporaryFile() as h:
                    h.truncate(limit // 8)
                    check_sending_mail(mail, [h.name], mail, password, True)


if __name__ == '__main__':
    main()
