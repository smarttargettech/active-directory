#!/usr/share/ucs-test/runner python3
## desc: IMAP mail login
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]
## bugs: []

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mailclient import MailClient_SSL


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        univention.config_registry.handler_set([
            'mail/dovecot/logging/auth_debug=yes',
            'mail/dovecot/logging/auth_debug_passwords=yes', 'mail/dovecot/logging/auth_verbose=yes',
            'mail/dovecot/logging/auth_verbose_passwords=yes', 'mail/dovecot/logging/mail_debug=yes'])
        autocallcmd1 = ['doveadm', 'reload']
        autocallcmd2 = ['doveadm', 'log', 'reopen']
        logfiles = ['/var/log/auth.log', '/var/log/univention/listener.log', '/var/log/dovecot.log']
        with utils.AutoCallCommand(enter_cmd=autocallcmd1, exit_cmd=autocallcmd1):
            with udm_test.UCSTestUDM() as udm:
                with utils.FollowLogfile(logfiles=logfiles):
                    with utils.AutoCallCommand(enter_cmd=autocallcmd2, exit_cmd=autocallcmd2):
                        password = uts.random_string()
                        mailAddress = '%s@%s' % (uts.random_name(), ucr.get('domainname'))
                        udm.create_user(
                            password=password,
                            mailPrimaryAddress=mailAddress,
                        )
                        try:
                            print('* Test imap login with the correct password:')
                            imap = MailClient_SSL('%(hostname)s.%(domainname)s' % ucr)
                            if imap.login_ok(mailAddress, password):
                                utils.fail('IMAP login failed with the correct password')

                            print('* Test imap login with the wrong password:')
                            imap = MailClient_SSL('%(hostname)s.%(domainname)s' % ucr)
                            if imap.login_ok(mailAddress, uts.random_name(), expected_to_succeed=False):
                                utils.fail('IMAP login succeeded with the wrong password')
                        finally:
                            try:
                                imap.logout()
                            except Exception:
                                pass
                            try:
                                imap.shutdown()
                            except Exception:
                                pass
                            imap = None


if __name__ == '__main__':
    main()
