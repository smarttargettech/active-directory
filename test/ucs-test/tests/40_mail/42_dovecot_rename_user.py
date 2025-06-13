#!/usr/share/ucs-test/runner python3
## desc: Dovecot, test username modrdn while keeping mail primary address
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import os
import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import get_dovecot_maildir, imap_search_mail, random_email, send_mail


timeout = 10


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            ucr.handler_set(['mail/dovecot/auth/cache_size=0'])
            subprocess.call(['systemctl', 'restart', 'dovecot'])
            userbase = []
            fqdn = '%(hostname)s.%(domainname)s' % ucr
            #
            # create some test users
            #
            for i in range(4):
                user_addr = random_email()
                user_dn, user_name = udm.create_user(
                    set={
                        'mailHomeServer': fqdn,
                        'mailPrimaryAddress': user_addr,
                    })
                msgid = uts.random_name()
                userbase.append((user_dn, user_name, user_addr, msgid))

            #
            # send email to each user
            #
            for _dn, _name, addr, msgid in userbase:
                send_mail(recipients=[addr], messageid=msgid, server=fqdn)
            loopcnt = 60
            while loopcnt > 0:
                loopcnt -= 1
                found = 0
                for _dn, _name, addr, msgid in userbase:
                    if imap_search_mail(messageid=msgid, server=fqdn, imap_user=addr, imap_folder='INBOX', use_ssl=True):
                        found += 1
                print('Found %d of %d mails' % (found, len(userbase)))
                if found == len(userbase):
                    break
                time.sleep(1)
            if loopcnt == 0:
                utils.fail('Could only deliver %d of %d mails to test users' % (found, len(userbase)))

            #
            # test renaming user object with all flag combinations
            #
            for i, flag_rename, flag_delete in [
                    (0, 'no', 'no'),
                    (1, 'no', 'yes'),
                    (2, 'yes', 'no'),
                    (3, 'yes', 'yes'),
            ]:
                old_dir = get_dovecot_maildir(userbase[i][2])
                if not os.path.exists(old_dir):
                    utils.fail('Test %d: old_dir = %r does not exist! %r' % (i, old_dir, userbase[i]))
                handler_set([
                    'mail/dovecot/mailbox/rename=%s' % (flag_rename,),
                    'mail/dovecot/mailbox/delete=%s' % (flag_delete,),
                ])
                subprocess.call(['systemctl', 'restart', 'univention-directory-listener'])
                udm.modify_object('users/user', dn=userbase[i][0], set={'username': '%scopy' % (userbase[i][1],)}, check_for_drs_replication=True)

                if not os.path.exists(old_dir):
                    utils.fail('Test %d: old_dir = %r has been removed unexpectedly! %r' % (i, old_dir, userbase[i]))
                try:
                    if not imap_search_mail(messageid=userbase[i][3], server=fqdn, imap_user=userbase[i][2], imap_folder='INBOX', use_ssl=True):
                        utils.fail('Test %d: msgid not found unexpectedly' % (i,))
                except Exception as ex:
                    print('EXCEPTION in imap_search_mail: %r' % (ex,))
                    utils.fail('Test %d: login to IMAP mailbox %r is not possible' % (i, userbase[i][2]))


if __name__ == '__main__':
    main()
