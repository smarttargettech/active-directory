#!/usr/share/ucs-test/runner python3
## desc: Check authenticated delivery via port 25, 465 and 587
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import send_mail


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            domain = ucr.get('domainname')
            univention.config_registry.handler_set([
                'mail/dovecot/logging/auth_debug=yes',
                'mail/dovecot/logging/auth_debug_passwords=yes', 'mail/dovecot/logging/auth_verbose=yes',
                'mail/dovecot/logging/auth_verbose_passwords=yes', 'mail/dovecot/logging/mail_debug=yes'])

            recipient_email = '%s@%s' % (uts.random_name(), domain)
            password = 'univention'
            _userdn, _username = udm.create_user(
                set={
                    'password': password,
                    'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                    'mailPrimaryAddress': recipient_email,
                },
            )

            # to local address
            for port, tls, ssl, failure_expected in (
                    (25, False, False, True),
                    (25, True, False, True),
                    (25, False, True, True),
                    # (465, False, False, True),  # disabled because non-SSL connection will wait data from server and
                    # (465, True, False, True),   # postfix' SSL port will wait for data from client ==> deadlock
                    (465, False, True, False),
                    (587, False, False, True),
                    (587, True, False, False),
                    (587, False, True, True),
            ):
                print('Testing port=%r tls=%r ssl=%r failure_expected=%r...' % (port, tls, ssl, failure_expected))
                try:
                    result = send_mail(sender=recipient_email, recipients=['noreply@univention.de'], port=port, tls=tls, ssl=ssl, username=recipient_email, password='univention')
                    if failure_expected:
                        print('TEST (port=%r,tls=%r,ssl=%r,exception expected=%r) = ERROR: UNEXPECTED SUCCESS: %r' % (port, tls, ssl, failure_expected, result))
                        utils.fail('mail unexpectedly sent')
                    else:
                        print('TEST (port=%r,tls=%r,ssl=%r,exception expected=%r) = SUCCESS: %r' % (port, tls, ssl, failure_expected, result))
                except Exception as ex:
                    if failure_expected:
                        print('TEST (port=%r,tls=%r,ssl=%r,exception expected=%r) = exception as expected: %r' % (port, tls, ssl, failure_expected, ex))
                    else:
                        print('TEST (port=%r,tls=%r,ssl=%r,exception expected=%r) = ERROR: UNEXPECTED EXCEPTION: %r' % (port, tls, ssl, failure_expected, ex))
                        raise


if __name__ == '__main__':
    main()
