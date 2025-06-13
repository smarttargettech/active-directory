#!/usr/share/ucs-test/runner python3
## desc: Create subfolder in shared folder and check permissions
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import os
import subprocess
import sys
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import (
    ImapMail, check_delivery, create_shared_mailfolder, get_dovecot_shared_folder_maildir, random_email, send_mail,
)


TIMEOUT_MAIL = 120


def main():
    if utils.package_installed('univention-samba4'):
        print('Skip test case in case Samba 4 is installed, see https://forge.univention.org/bugzilla/show_bug.cgi?id=46191')
        sys.exit(137)

    with udm_test.UCSTestUDM() as udm, ucr_test.UCSTestConfigRegistry() as ucr:
        ucr.handler_set(['mail/dovecot/auth/cache_size=0'])
        subprocess.call(['systemctl', 'restart', 'dovecot'])
        fqdn = '%(hostname)s.%(domainname)s' % ucr
        user_addr1 = random_email()
        _user_dn1, _user_name1 = udm.create_user(
            set={
                'mailHomeServer': fqdn,
                'mailPrimaryAddress': user_addr1,
            })
        user_addr2 = random_email()
        _user_dn2, _user_name2 = udm.create_user(
            set={
                'mailHomeServer': fqdn,
                'mailPrimaryAddress': user_addr2,
            })

        token = uts.random_name()
        send_mail(recipients=[user_addr1, user_addr2], msg=token, subject='Test')
        check_delivery(token, user_addr1, True)
        check_delivery(token, user_addr2, True)

        print('*** OK: mails were received by users')

        for with_email in (True, False):
            print('***** Testing shared folder {} email address *****'.format('with' if with_email else 'without'))
            _folder_dn, folder_name, _folder_address = create_shared_mailfolder(
                udm,
                fqdn,
                mailAddress=random_email() if with_email else None,
                user_permission=[
                    '"{}" "{}"'.format(user_addr1, 'all'),
                    '"{}" "{}"'.format(user_addr2, 'read'),
                ],
            )
            utils.wait_for_replication()

            folder_path = get_dovecot_shared_folder_maildir(folder_name)
            if not os.path.exists(folder_path):
                utils.fail(f'Maildir {folder_path!r} for shared folder does not exist!')
            print(f'*** OK: shared folder created in {folder_path!r}.')

            # The list returned by connection.list is broken after loggin with user_addr1 again
            # Since the reason for this is not clear yet the first instance of the ImapMail class
            # with user1 still logged in is kept until the subfolder is created.

            imap1 = ImapMail()
            imap1.get_connection('localhost', user_addr1, 'univention')
            retry = TIMEOUT_MAIL
            while True:
                try:
                    imap1.copy('1', 'INBOX', folder_name)
                    break
                except AssertionError as exc:
                    if retry > 0:
                        print(f'*** Error, retrying ({retry}/{TIMEOUT_MAIL}): {exc}')
                        time.sleep(5)
                        retry -= 5
                    else:
                        raise
            # imap1.connection.logout()

            print('*** OK: user1 can write to shared folder')

            imap = ImapMail()
            imap.get_connection('localhost', user_addr2, 'univention')
            try:
                imap.copy('1', 'INBOX', folder_name)
                utils.fail('User with read-only permission copied message to shared folder.')
            except AssertionError:
                print('*** OK: user2 cannot write to shared folder')
            imap.connection.logout()

            subfolder_name1 = imap1.create_subfolder(folder_name, uts.random_name())
            print('*** OK: user1 can create subfolder')
            imap1.copy('1', 'INBOX', subfolder_name1)
            print('*** OK: user1 can write to subfolder')
            imap1.connection.logout()

            imap = ImapMail()
            imap.get_connection('localhost', user_addr2, 'univention')
            try:
                imap.copy('1', 'INBOX', subfolder_name1)
                utils.fail('User with read-only permission wrote to subfolder created by user1.')
            except AssertionError:
                print('*** OK: user2 cannot write to subfolder created by user1')
            try:
                imap.create_subfolder(folder_name, uts.random_name())
                utils.fail('User with read-only permission created subfolder.')
            except AssertionError:
                print('*** OK: user2 cannot create subfolder')
            try:
                imap.delete_folder(subfolder_name1)
                utils.fail('User with read-only permission deleted subfolder created by user1..')
            except AssertionError:
                print('*** OK: user2 cannot delete subfolder created by user1.')
            imap.connection.logout()

            imap = ImapMail()
            imap.get_connection('localhost', user_addr1, 'univention')
            imap.delete_folder(subfolder_name1)
            print('*** OK: user1 can delete subfolder created by user1.')
            imap.connection.logout()

        print('*** Test ended successfully.')


if __name__ == '__main__':
    global timeout  # noqa: PLW0604
    timeout = 1
    main()
