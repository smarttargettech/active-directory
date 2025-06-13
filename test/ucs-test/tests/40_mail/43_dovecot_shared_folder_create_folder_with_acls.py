#!/usr/share/ucs-test/runner python3
## desc: Create and remove a shared folders with ACLs with whitespace-containing group names
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import sys

import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import create_shared_mailfolder, random_email
from essential.mailclient import MailClient_SSL


TIMEOUT_MAIL = 10


def main() -> None:
    if utils.package_installed('univention-samba4'):
        print('Skip test case in case Samba 4 is installed, see https://forge.univention.org/bugzilla/show_bug.cgi?id=46191')
        sys.exit(137)

    with utils.AutomaticListenerRestart():
        with udm_test.UCSTestUDM() as udm:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                handler_set([
                    'mail/dovecot/logging/auth_debug=yes', 'mail/dovecot/logging/auth_debug_passwords=yes',
                    'mail/dovecot/logging/auth_verbose=yes', 'mail/dovecot/logging/auth_verbose_passwords=yes',
                    'mail/dovecot/logging/mail_debug=yes', 'mail/dovecot/mailbox/rename=yes',
                    'mail/dovecot/mailbox/delete=yes'])
                utils.restart_listener()
                utils.wait_for_replication()
                logfiles = ['/var/log/dovecot.log', '/var/log/univention/listener.log']
                with utils.FollowLogfile(logfiles=logfiles):
                    with utils.AutoCallCommand(enter_cmd=['doveadm', 'log', 'reopen'], exit_cmd=['doveadm', 'log', 'reopen']):
                        fqdn = '%(hostname)s.%(domainname)s' % ucr
                        user_address = random_email()
                        user_password = 'univention'
                        _user_dn, _user_name = udm.create_user(
                            set={
                                'mailHomeServer': fqdn,
                                'mailPrimaryAddress': user_address,
                                'password': user_password,
                            })

                        # use some groups with space character within its name
                        group_acls = [
                            ("Domain Admins", "all"),
                            ("Domain Users", "read"),
                            ("Computers", "append"),
                        ]
                        user_acls = ['"%s" "%s"' % (user_address, 'all')]
                        # create folder
                        folder_dn, folder_name, _folder_address = create_shared_mailfolder(
                            udm,
                            fqdn,
                            mailAddress=False,
                            user_permission=user_acls,
                            group_permission=[f'"{grpname}" "{right}"' for grpname, right in group_acls],
                        )
                        utils.wait_for_replication()
                        print(f'*** Folder: {folder_name!r} --> {folder_dn!r}')

                        # read folder's ACLs
                        imap = MailClient_SSL(fqdn)
                        imap.log_in(user_address, user_password)
                        mailbox_acls = imap.get_acl(folder_name)
                        imap.logout()
                        print(repr(mailbox_acls))
                        acls = mailbox_acls[folder_name]
                        print(repr(acls))

                        # verify that acls for groups are set
                        for grpname, _right in group_acls:
                            assert f'${grpname}' in acls, f"'${grpname}' not in ACL list"
                        assert user_address in acls, f'{user_address} not in ACL list'

                        udm.remove_object('mail/folder', dn=folder_dn)


if __name__ == '__main__':
    global timeout  # noqa: PLW0604
    timeout = 1
    main()
