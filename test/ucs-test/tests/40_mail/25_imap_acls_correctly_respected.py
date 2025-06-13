#!/usr/share/ucs-test/runner python3
## desc: Mail imap acl flags are correctly respected by the IMAP server
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import itertools
import subprocess

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import create_shared_mailfolder
from essential.mailclient import MailClient_SSL


def main():
    with udm_test.UCSTestUDM() as udm:
        ucr_tmp = univention.config_registry.ConfigRegistry()
        ucr_tmp.load()
        cmd = ['/etc/init.d/dovecot', 'restart']
        with utils.AutoCallCommand(exit_cmd=cmd, stderr=open('/dev/null', 'w')):
            with ucr_test.UCSTestConfigRegistry() as ucr:
                domain = ucr.get('domainname')
                univention.config_registry.handler_set(['mail/dovecot/mailbox/delete=yes'])
                subprocess.call(['/etc/init.d/dovecot', 'restart'], stderr=open('/dev/null', 'w'))
                host = '%s.%s' % (ucr.get('hostname'), domain)
                password = 'univention'
                mails = []
                users = []
                for i in range(3):
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
                default_shared_permissions = {'anyone': 'lrswipkxtecda'}
                permissions = 'lrswipkxtecda'
                _shared_dn, shared_mailbox, _shared_address = create_shared_mailfolder(
                    udm, host, mailAddress=True, user_permission=['"%s" "%s"' % ('anyone', 'all')])

                test_cases = itertools.product(mails[0:2], permissions)
                for i in range(len(mails[0:2]) * len(permissions)):
                    who, what = next(test_cases)
                    imap = MailClient_SSL(host)
                    imap.log_in(mails[2], password)
                    mailboxs = imap.getMailBoxes()
                    mailboxs.append(shared_mailbox)
                    for mailbox in mailboxs:
                        print('%d: Mailbox = %s, %s -> %s' % (i, mailbox, who, what))
                        imap.deleteacl(mailbox, who)
                        if mailbox == shared_mailbox:
                            imap.check_acls({mailbox: default_shared_permissions})
                        imap.setacl(mailbox, who, what)
                        imap.check_acls({mailbox: {who: what}})
                    imap.logout()


if __name__ == '__main__':
    main()
