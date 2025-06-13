#!/usr/share/ucs-test/runner python3
## desc: sieve script
## tags: []
## exposure: dangerous
## packages: [univention-mail-server, sieve-connect]

import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import check_delivery, send_mail


def sieve_test(mail, expected_output):
    """Calls sieve-test"""
    cmd = [
        "sieve-connect",
        "--user", mail,
        "--server", "localhost",
        "--notlsverify", "--nosslverify",
        "--remotesieve", "default",
        "--list",
    ]
    print('**', cmd)
    pop = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    out, err = pop.communicate(input=b'univention\n')
    if expected_output.encode('UTF-8') not in out:
        utils.fail(out, err)


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            handler_set(['mail/dovecot/sieve/spam=true'])
            utils.restart_listener()
            domain = ucr.get('domainname')
            host = '%s.%s' % (ucr.get('hostname'), domain)
            password = 'univention'
            usermail = '%s@%s' % (uts.random_name(), domain)
            _userdn, _username = udm.create_user(
                set={
                    'password': password,
                    'mailHomeServer': host,
                    'mailPrimaryAddress': usermail,
                },
            )

            sieve_test(usermail, '"default" ACTIVE')
            token = str(time.time())
            send_mail(recipients=usermail, msg=token, gtube=True)
            check_delivery(token, recipient_email=usermail, should_be_delivered=True, spam=True)

            handler_set(['mail/dovecot/sieve/spam=false'])
            utils.restart_listener()
            usermail = '%s@%s' % (uts.random_name(), domain)
            _userdn, _username = udm.create_user(
                set={
                    'password': password,
                    'mailHomeServer': host,
                    'mailPrimaryAddress': usermail,
                },
            )
            sieve_test(usermail, '')
            token = str(time.time())
            send_mail(recipients=usermail, msg=token, gtube=True)
            check_delivery(token, recipient_email=usermail, should_be_delivered=False, spam=True)


if __name__ == '__main__':
    main()
