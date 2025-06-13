#!/usr/share/ucs-test/runner python3
## desc: Mail delivery via submission port
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.network import NetworkRedirector

from essential.mail import check_sending_mail, deactivate_spam_detection, reload_amavis_postfix


def main():
    with NetworkRedirector() as nethelper:
        with udm_test.UCSTestUDM() as udm:
            try:
                with ucr_test.UCSTestConfigRegistry() as ucr:
                    deactivate_spam_detection()
                    reload_amavis_postfix()
                    domain = ucr.get('domainname')
                    univention.config_registry.handler_set([
                        'mail/dovecot/logging/auth_debug=yes',
                        'mail/dovecot/logging/auth_debug_passwords=yes', 'mail/dovecot/logging/auth_verbose=yes',
                        'mail/dovecot/logging/auth_verbose_passwords=yes', 'mail/dovecot/logging/mail_debug=yes'])
                    with utils.FollowLogfile(logfiles=['/var/log/auth.log', '/var/log/mail.log']):
                        recipient_email = '%s@%s' % (uts.random_name(), domain)
                        password = 'univention'
                        _userdn, _username = udm.create_user(
                            set={
                                'password': password,
                                'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                                'mailPrimaryAddress': recipient_email,
                            },
                        )
                        nethelper.add_loop('1.2.3.4', '4.3.2.1')

                        # to local address
                        check_sending_mail(recipient_email, password, recipient_email, tls=True)
                        check_sending_mail(None, None, recipient_email, tls=True, allowed=True)
                        check_sending_mail(recipient_email, password, recipient_email, tls=False, allowed=False)
                        check_sending_mail(None, None, recipient_email, tls=False, allowed=False)

                        # to foreign address
                        check_sending_mail(recipient_email, password, 'noreply@univention.de', tls=True, local=False)
                        check_sending_mail(None, None, 'noreply@univention.de', tls=True, allowed=False, local=False)
                        check_sending_mail(recipient_email, password, 'noreply@univention.de', tls=False, allowed=False, local=False)
                        check_sending_mail(None, None, 'noreply@univention.de', tls=False, allowed=False, local=False)
            finally:
                reload_amavis_postfix()


if __name__ == '__main__':
    main()
