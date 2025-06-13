#!/usr/share/ucs-test/runner python3
## desc: Modification of user's mail primary address
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import os
import subprocess
from time import sleep

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import get_dovecot_maildir, imap_search_mail, random_email, send_mail


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
                else:
                    sleep(1)
                if loopcnt == 15:
                    print('There are still mails missing - trying to force postfix to deliver mails:')
                    subprocess.call(['/usr/sbin/postqueue', '-f'])
            if loopcnt == 0:
                print('Not all mails have been delivered yet. Running /usr/bin/mailq:')
                subprocess.call(['/usr/bin/mailq'])
                utils.fail('Could only deliver %d of %d mails to test users' % (found, len(userbase)))

            #
            # test changing mail primary address with all flag combinations
            #
            for i, flag_rename, flag_delete in [
                    (0, 'no', 'no'),
                    (1, 'no', 'yes'),
                    (2, 'yes', 'no'),
                    (3, 'yes', 'yes')]:
                old_dir = get_dovecot_maildir(userbase[i][2])
                if not os.path.exists(old_dir):
                    utils.fail('Test %d: old_dir = %r does not exist! %r' % (i, old_dir, userbase[i]))
                handler_set([
                    'mail/dovecot/mailbox/rename=%s' % (flag_rename,),
                    'mail/dovecot/mailbox/delete=%s' % (flag_delete,),
                ])
                subprocess.call(['systemctl', 'restart', 'univention-directory-listener'])
                new_mpa = random_email()
                udm.modify_object('users/user', dn=userbase[i][0], set={'mailPrimaryAddress': new_mpa}, check_for_drs_replication=True)

                new_dir = get_dovecot_maildir(new_mpa)
                if not os.path.exists(new_dir):
                    utils.fail('Test %d: new_dir = %r does not exist! %r' % (i, new_dir, userbase[i]))

                if i == 0:
                    if not os.path.exists(old_dir):
                        utils.fail('Test %d: old_dir = %r has been removed unexpectedly! %r' % (i, old_dir, userbase[i]))
                    if imap_search_mail(messageid=userbase[i][3], server=fqdn, imap_user=new_mpa, imap_folder='INBOX', use_ssl=True):
                        utils.fail('Test %d: msgid found unexpectedly' % (i,))
                elif i == 1:
                    if os.path.exists(old_dir):
                        utils.fail('Test %d: old_dir = %r has not been removed! %r' % (i, old_dir, userbase[i]))
                    if imap_search_mail(messageid=userbase[i][3], server=fqdn, imap_user=new_mpa, imap_folder='INBOX', use_ssl=True):
                        utils.fail('Test %d: msgid found unexpectedly' % (i,))
                elif i in (2, 3):
                    if os.path.exists(old_dir):
                        utils.fail('Test %d: old_dir = %r has not been renamed! %r' % (i, old_dir, userbase[i]))
                    cnt = imap_search_mail(messageid=userbase[i][3], server=fqdn, imap_user=new_mpa, imap_folder='INBOX', use_ssl=True)
                    if not cnt:
                        print('Test %d: maildir does not contain old mails: cnt=%d' % (i, cnt))
                        utils.fail('Test %d: maildir does not contain old mails' % (i,))


if __name__ == '__main__':
    main()
