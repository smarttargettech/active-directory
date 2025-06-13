#!/usr/share/ucs-test/runner python3
## desc: Delivery to deactivated local account
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set

from essential.mail import check_delivery, send_mail


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            domain = ucr.get('domainname')
            handler_set(['mail/dovecot/mailbox/delete=yes'])
            subprocess.call(['/etc/init.d/dovecot', 'restart'], stderr=open('/dev/null', 'w'))
            host = '%s.%s' % (ucr.get('hostname'), domain)
            password = 'univention'
            usermail1 = '%s@%s' % (uts.random_name(), domain)
            udm.create_user(
                set={
                    'password': password,
                    'mailHomeServer': host,
                    'mailPrimaryAddress': usermail1,
                    'disabled': '1',
                },
            )
            usermail = '%s@%s' % (uts.random_name(), domain)
            udm.create_user(
                set={
                    'password': password,
                    'mailHomeServer': host,
                    'mailPrimaryAddress': usermail,
                },
            )
            token = str(time.time())
            send_mail(recipients=usermail1, msg=token, tls=True, username=usermail, password=password)
            check_delivery(token, usermail1, True)


if __name__ == '__main__':
    main()
