#!/usr/share/ucs-test/runner python3
## desc: Test Dovecots mailquota support
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools
## bugs: [38727]
import email
import imaplib
import subprocess
import time

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import ImapMail, mail_delivered
from essential.mailclient import MailClient


timeout = 1


def main():
    with udm_test.UCSTestUDM() as udm:
        cmd = ['/etc/init.d/dovecot', 'restart']
        with utils.AutoCallCommand(exit_cmd=cmd, stderr=open('/dev/null', 'w')):
            with ucr_test.UCSTestConfigRegistry() as ucr:
                univention.config_registry.handler_set(['mail/dovecot/auth/cache_size=0'])
                subprocess.call(['/etc/init.d/dovecot', 'restart'], stderr=open('/dev/null', 'w'))
                quota01 = 5
                domain = ucr.get('domainname')
                pw = 'univention'
                mail = '%s@%s' % (uts.random_name(), domain)
                userdn, _username = udm.create_user(
                    password=pw,
                    set={
                        "mailHomeServer": '%s.%s' % (ucr.get("hostname"), domain),
                        "mailPrimaryAddress": mail,
                        "mailUserQuota": str(quota01),
                    },
                )

                #
                # quota set with UDM should be reflected by IMAP4.getquota()
                # dovecot equivalent to 08create_modify_remove_mailquota
                #
                quota02 = 10
                quota03 = 0

                # create quota (already done above in udm.create_user())
                imap = ImapMail(timeout=timeout)
                imap.login_OK(mail, pw)
                quota, response = imap.get_imap_quota(mail, pw)
                if response != 'OK':
                    utils.fail('Fail get imap quota')
                if quota != quota01 * 1024:
                    utils.fail('Wrong quota, expected: %d, got %r' % (quota01 * 1024, quota))

                # modify quota
                udm.modify_object(modulename='users/user', dn=userdn, mailUserQuota=str(quota02))

                quota, response = imap.get_imap_quota(mail, pw)
                if response != 'OK':
                    utils.fail('Fail get imap quota')
                if quota != quota02 * 1024:
                    utils.fail('Wrong quota, expected: %d, got %r' % (quota02 * 1024, quota))

                # remove quota
                udm.modify_object(modulename='users/user', dn=userdn, mailUserQuota=str(quota03))

                quota, response = imap.get_imap_quota(mail, pw)
                if response != 'OK':
                    utils.fail('Fail get imap quota')
                if quota != -1:
                    utils.fail('Wrong quota set = %r, although it should not be set' % quota)

                #
                # going over mail/dovecot/quota/warning/text/PERCENT=TEXT percent of quota should trigger a warning
                # message TEXT with subject mail/dovecot/quota/warning/subject
                #
                quota04 = 2
                percent = 50
                token_body = "my_message %s" % str(time.time())
                univention.config_registry.handler_set(["mail/dovecot/quota/warning/text/%d=%s" % (percent, token_body)])
                subprocess.call(["/usr/bin/doveadm", "reload"])
                udm.modify_object(modulename='users/user', dn=userdn, mailUserQuota=str(quota04))
                msg = bytes(email.message_from_string("Lorem ipsum dolor sit amet, consetetur sadipscing " * quota04 * 12000))
                imap = MailClient("localhost")
                imap.login(mail, pw)
                imap.select("INBOX")
                imap.append("INBOX", "", imaplib.Time2Internaldate(time.time()), msg)
                if not mail_delivered(token_body, mail_address=mail):
                    utils.fail("Fail: quota warn message delivery missing (quota was set to %d MB, warn message expected above %d percent, uploaded message of length %0.3f MB)." % (quota04, percent, len(msg) / 1024.0 / 1024.0))

                #
                # user over quota should not be able to IMAP4.append()
                #
                msg = bytes(email.message_from_string("Lorem ipsum dolor sit amet, consetetur sadipscing " * quota04 * 10000))
                imap = MailClient("localhost")
                imap.login(mail, pw)
                imap.select("INBOX")
                result, txt = imap.append("INBOX", "", imaplib.Time2Internaldate(time.time()), msg)
                if result != "NO":
                    utils.fail("Fail: message upload should have failed with 'OVERQUOTA'. imap.append() returned: (%s, %s)" % (result, txt))


if __name__ == '__main__':
    main()
