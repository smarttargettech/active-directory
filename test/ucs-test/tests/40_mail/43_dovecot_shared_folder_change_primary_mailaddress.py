#!/usr/share/ucs-test/runner python3
## desc: Change primary mail address of shared folders
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import os
import sys
import syslog
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import create_shared_mailfolder, get_dovecot_maildir, imap_search_mail, random_email, send_mail


TIMEOUT_MAIL = 120


class Bunch:

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __repr__(self):
        return repr(self.__dict__)


def main():
    logfiles = ['/var/log/dovecot.log', '/var/log/mail.log']

    if utils.package_installed('univention-samba4'):
        print('Skip test case in case Samba 4 is installed, see https://forge.univention.org/bugzilla/show_bug.cgi?id=46190')
        sys.exit(137)

    with utils.AutomaticListenerRestart(), udm_test.UCSTestUDM() as udm, ucr_test.UCSTestConfigRegistry() as ucr, utils.FollowLogfile(logfiles=logfiles):
        syslog.openlog(facility=syslog.LOG_MAIL)  # get markers in mail.log in case of error
        fqdn = '%(hostname)s.%(domainname)s' % ucr
        user_addr = random_email()
        _user_dn, _user_name = udm.create_user(
            set={
                'mailHomeServer': fqdn,
                'mailPrimaryAddress': user_addr,
            })

        # create folder with mailPrimaryAddress (mpa)
        dn, name, address = create_shared_mailfolder(udm, fqdn, mailAddress=True, user_permission=['"%s" "%s"' % (user_addr, 'all')])
        folder = Bunch(dn=dn, name=name, mail_address=address)

        # check folder with mail address
        path = get_dovecot_maildir(folder.mail_address)
        if not os.path.exists(path):
            utils.fail('Maildir %r for shared folder with mail address does not exist! %r' % (path, folder))

        #
        # test changing mail primary address with all flag combinations
        #
        new_address = folder.mail_address
        for i, flag_rename, flag_delete in [
                (0, 'no', 'no'),
                (1, 'no', 'yes'),
                (2, 'yes', 'no'),
                (3, 'yes', 'yes'),
        ]:
            old_address = new_address
            new_address = random_email()

            #
            # reconfigure system
            #
            ucr_settings = [
                'mail/dovecot/mailbox/rename=%s' % (flag_rename,),
                'mail/dovecot/mailbox/delete=%s' % (flag_delete,),
            ]
            handler_set(ucr_settings)
            utils.restart_listener()
            utils.wait_for_replication()

            #
            # send email to each shared folder with mail address
            #
            print(f'Sending with settings {ucr_settings}')
            syslog.syslog(syslog.LOG_INFO, f'Sending with settings {ucr_settings}.')
            msgid = uts.random_name()
            send_mail(recipients=[old_address], messageid=msgid, server=fqdn)
            for _ in range(TIMEOUT_MAIL):
                try:
                    found = imap_search_mail(messageid=msgid, server=fqdn, imap_user=user_addr, imap_folder='shared/%s' % (old_address,), use_ssl=True)
                except AssertionError as exc:
                    print(exc)
                    found = False
                if found:
                    print('Found mail in shared folder sent to %r' % ('shared/%s' % (old_address,),))
                    syslog.syslog(syslog.LOG_INFO, f'Found mail in shared folder sent to shared/{old_address}')
                    break
                time.sleep(1)
            else:
                utils.fail('Test %d: Could not deliver test mail with msgid %r to shared folder' % (i, msgid))

            old_dir = get_dovecot_maildir(old_address)
            if not os.path.exists(old_dir):
                utils.fail('Test %d: old_dir = %r does not exist! %r' % (i, old_dir, folder))

            new_dir = get_dovecot_maildir(new_address)
            if os.path.exists(new_dir):
                utils.fail('Test %d: new_dir = %r does not exist! %r' % (i, new_dir, folder))

            print('\n\n==> MODIFYING ADDRESS OF SHARED FOLDER FROM %r to %r' % (old_address, new_address))
            print('==> FOLDER OLD: %r' % (old_dir,))
            print('==> FOLDER NEW: %r' % (new_dir,))
            print('==> RENAME=%r' % (flag_rename,))
            print('==> DELETE=%r' % (flag_delete,))
            udm.modify_object('mail/folder', dn=folder.dn, set={'mailPrimaryAddress': new_address})

            if os.path.exists(old_dir):
                utils.fail('Test %d: old_dir = %r has not been renamed! %r' % (i, old_dir, folder))
            cnt = imap_search_mail(messageid=msgid, server=fqdn, imap_user=user_addr, imap_folder='shared/%s' % (new_address,), use_ssl=True)
            if not cnt:
                print('Test %d: maildir does not contain old mails: cnt=%d' % (i, cnt))
                time.sleep(180)
                utils.fail('Test %d: maildir does not contain old mails' % (i,))

        #
        # remove shared folder
        #
        folder.mail_address = new_address
        udm.remove_object('mail/folder', dn=folder.dn)

        # check folder with mail address
        path = get_dovecot_maildir(folder.mail_address)
        if os.path.exists(path):
            utils.fail('Maildir %r for shared folder with mail address has not been removed! %r' % (path, folder))


if __name__ == '__main__':
    global timeout  # noqa: PLW0604
    timeout = 1
    main()
