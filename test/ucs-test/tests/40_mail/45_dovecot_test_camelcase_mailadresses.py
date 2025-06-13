#!/usr/share/ucs-test/runner python3
## desc: Dovecot, test behavior if mail address is specified in mixed case
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import os
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
import univention.uldap
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import file_search_mail, get_dovecot_maildir, random_email, send_mail


timeout = 10


class Bunch:

    def __init__(self, **kwds):
        self.__dict__.update(kwds)


def get_mixed_case_maildir(addr):
    localpart, domain = addr.rsplit('@', 1)
    return '/var/spool/dovecot/private/%s/%s/Maildir' % (domain, localpart)


def main():
    cmd = ['systemctl', 'restart', 'univention-directory-listener']
    with ucr_test.UCSTestConfigRegistry() as ucr:
        handler_set([
            'mail/dovecot/mailbox/delete=yes',
            'mail/dovecot/mailbox/rename=yes',
        ])
        with utils.AutoCallCommand(enter_cmd=cmd, exit_cmd=cmd):
            with udm_test.UCSTestUDM() as udm:
                userbase = []
                admin_account = ucr.get("tests/domainadmin/account", "uid=Administrator,cn=users,{}".format(ucr["ldap/base"]))
                pwd_file = ucr.get("tests/domainadmin/pwdfile")
                if pwd_file:
                    with open(pwd_file) as fp:
                        password = fp.read().strip()
                else:
                    password = "univention"
                lo = univention.uldap.access(
                    host=ucr["ldap/master"],
                    port=int(ucr["ldap/master/port"]),
                    base=ucr["ldap/base"],
                    binddn=admin_account,
                    bindpw=password,
                )

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

                    if i == 0:
                        new_addr = user_addr.lower()
                    elif i == 1:
                        new_addr = user_addr.upper()
                    elif i == 2:
                        new_addr = user_addr[0:3].upper() + user_addr[3:].lower()
                    elif i == 3:
                        new_addr = user_addr[:-5].upper() + user_addr[-5:].lower()
                    lo.modify(user_dn, [('mailPrimaryAddress', user_addr.encode('UTF-8'), new_addr.encode('UTF-8'))])
                    user_addr = new_addr

                    userbase.append(Bunch(dn=user_dn, name=user_name, addr=user_addr, msgid=msgid))

                utils.wait_for_replication()

                # check if mailbox exists
                for user in userbase:
                    # HINT: use user.addr.lower() to check if the correct maildir is created (Bug #39346)
                    maildir = get_dovecot_maildir(user.addr)
                    if not os.path.isdir(maildir):
                        utils.fail('maildir for %r does not exist: %r' % (user.addr, maildir))
                    else:
                        print('OK: does exist: %r' % (maildir,))

                    mixed_case_maildir = get_mixed_case_maildir(user.addr)
                    if maildir != mixed_case_maildir:
                        if os.path.isdir(mixed_case_maildir):
                            utils.fail('mixed maildir for %r does exist: %r' % (user.addr, mixed_case_maildir))
                        else:
                            print('OK: does not exist: %r' % (mixed_case_maildir,))

                #
                # send email to each user
                #
                for user in userbase:
                    # HINT: use user.addr.lower() to check if the correct maildir is used when delivered by postfix (Bug #39346)
                    send_mail(recipients=[user.addr], messageid=user.msgid, server=fqdn)

                loopcnt = 60
                while loopcnt > 0:
                    loopcnt -= 1
                    found = 0
                    for user in userbase:
                        if file_search_mail(tokenlist=[user.msgid], mail_address=user.addr):
                            found += 1
                    print('Found %d of %d mails' % (found, len(userbase)))
                    if found == len(userbase):
                        break
                    time.sleep(1)
                if loopcnt == 0:
                    utils.fail('Could only deliver %d of %d mails to test users' % (found, len(userbase)))

                # check if mailbox exists
                for user in userbase:
                    # HINT: use user.addr.lower() to check if the correct maildir is created (Bug #39346)
                    maildir = get_dovecot_maildir(user.addr)
                    if not os.path.isdir(maildir):
                        utils.fail('maildir for %r does not exist: %r' % (user.addr, maildir))
                    else:
                        print('OK: does exist: %r' % (maildir,))

                    mixed_case_maildir = get_mixed_case_maildir(user.addr)
                    if maildir != mixed_case_maildir:
                        if os.path.isdir(mixed_case_maildir):
                            utils.fail('mixed maildir for %r does exist: %r' % (user.addr, mixed_case_maildir))
                        else:
                            print('OK: does not exist: %r' % (mixed_case_maildir,))

                #
                # test removing user object
                #
                for user in userbase:
                    udm.remove_object('users/user', dn=user.dn)

                # check if mailboxes have been removed
                for user in userbase:
                    maildir = get_dovecot_maildir(user.addr.lower())   # HINT: use user.addr.lower() to check if the correct maildir is created (Bug #39346)
                    if os.path.isdir(maildir):
                        utils.fail('maildir for %r has not been removed: %r' % (user.addr, maildir))
                    else:
                        print('OK: does not exist: %r' % (maildir,))

                    mixed_case_maildir = get_mixed_case_maildir(user.addr)
                    if maildir != mixed_case_maildir:
                        if os.path.isdir(mixed_case_maildir):
                            utils.fail('maildir for %r does exist: %r' % (user.addr, mixed_case_maildir))
                        else:
                            print('OK: does not exist: %r' % (mixed_case_maildir,))


if __name__ == '__main__':
    main()
