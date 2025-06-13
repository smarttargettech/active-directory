#!/usr/share/ucs-test/runner python3
## desc: Mail imap acl flags are correctly evaluated
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]
## versions:
##  4.1-2: skip

import subprocess
import time

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import check_delivery, create_shared_mailfolder, send_mail
from essential.mailclient import MailClient_SSL


def main():
    with udm_test.UCSTestUDM() as udm:
        ucr_tmp = univention.config_registry.ConfigRegistry()
        ucr_tmp.load()
        domain = ucr_tmp.get('domainname').lower()  # remove lower() when Bug #39721 is fixed
        host = '%s.%s' % (ucr_tmp.get('hostname'), domain)

        cmd = ['/etc/init.d/dovecot', 'restart']
        with utils.AutoCallCommand(exit_cmd=cmd, stderr=open('/dev/null', 'w')):
            with ucr_test.UCSTestConfigRegistry():
                univention.config_registry.handler_set([
                    'mail/dovecot/mailbox/delete=yes',
                    'mail/dovecot/logging/auth_debug=yes', 'mail/dovecot/logging/auth_debug_passwords=yes',
                    'mail/dovecot/logging/auth_verbose=yes', 'mail/dovecot/logging/auth_verbose_passwords=yes',
                    'mail/dovecot/logging/mail_debug=yes'])
                autocallcmd1 = ['doveadm', 'reload']
                autocallcmd2 = ['doveadm', 'log', 'reopen']
                logfiles = ['/var/log/auth.log', '/var/log/univention/listener.log', '/var/log/dovecot.log']

                subprocess.call(['/etc/init.d/dovecot', 'restart'], stderr=open('/dev/null', 'w'))
                with utils.AutoCallCommand(enter_cmd=autocallcmd1, exit_cmd=autocallcmd1):
                    with utils.FollowLogfile(logfiles=logfiles):
                        with utils.AutoCallCommand(enter_cmd=autocallcmd2, exit_cmd=autocallcmd2):
                            password = 'univention'
                            mails = []
                            users = []
                            for _i in range(3):
                                usermail = '%s@%s' % (uts.random_name(), domain)
                                userdn, _username = udm.create_user(
                                    set={
                                        'password': password,
                                        'mailHomeServer': host,
                                        'mailPrimaryAddress': usermail,
                                    },
                                )
                                mails.append(usermail)
                                users.append(userdn)
                            token = str(time.time())
                            send_mail(recipients=mails, msg=token, port=587, tls=True, username=usermail, password=password, debuglevel=0)
                            check_delivery(token, mails[0], True)
                            group_mail = '%s@%s' % (uts.random_name(), domain)
                            _groupdn, groupname = udm.create_group(
                                set={
                                    'users': users[1],
                                    'mailAddress': group_mail,
                                },
                            )
                            permissions = {
                                'lookup': 'l',
                                'read': 'lrs',
                                'post': 'lrsp',
                                'append': 'lrspi',
                                'write': 'lrspiwcd',
                                'all': 'lrspiwcda',
                            }

                            create_shared_mailfolder(udm, host, mailAddress=False, user_permission=['"%s" "%s"' % ('anyone', 'none')])
                            create_shared_mailfolder(udm, host, mailAddress=True, user_permission=['"%s" "%s"' % ('anyone', 'none')])
                            utils.wait_for_replication()

                            owner_user = mails[0]
                            independent_user = mails[2]

                            for permission in permissions.values():
                                imap = MailClient_SSL(host)
                                imap.log_in(owner_user, password)
                                mailboxs = imap.getMailBoxes()
                                for mailbox in mailboxs:
                                    print('** %s Mailbox = %s, Setting %s -> %s' % (
                                        owner_user, mailbox, independent_user, permission))
                                    imap.setacl(mailbox, independent_user, permission)
                                    imap2 = MailClient_SSL(host)
                                    imap2.log_in(independent_user, password)
                                    imap2.check_permissions(owner_user, mailbox, permission)
                                    imap2.logout()
                                imap.logout()

                            group_user = mails[1]
                            groupname = '$%s' % groupname
                            for permission in [permissions.get(x) for x in permissions]:
                                imap = MailClient_SSL(host)
                                imap.log_in(owner_user, password)
                                mailbox = 'INBOX'
                                print('** %s Mailbox = %s, Setting %s -> %s' % (
                                    owner_user, mailbox, groupname, permission))
                                imap.setacl(mailbox, groupname, permission)
                                time.sleep(20)
                                imap2 = MailClient_SSL(host)
                                imap2.log_in(group_user, password)
                                imap2.check_permissions(owner_user, mailbox, permission)
                                imap2.logout()
                                imap.logout()


if __name__ == '__main__':
    main()
