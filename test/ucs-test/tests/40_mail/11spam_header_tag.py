#!/usr/share/ucs-test/runner python3
## desc: SPAM header tag test
## tags: [mail]
## exposure: dangerous
## packages: [univention-mail-server]
## bugs: [36907]

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

import essential.mail


def main():
    with udm_test.UCSTestUDM() as udm:
        try:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                password = uts.random_string()
                mailPrimaryAddress = '%s@%s' % (uts.random_name(), ucr.get('domainname'))
                mailHomeServer = '%(hostname)s.%(domainname)s' % ucr
                spam_folder = essential.mail.get_spam_folder_name()

                _userdn, _username = udm.create_user(
                    password=password,
                    set={
                        'mailHomeServer': mailHomeServer,
                        'mailPrimaryAddress': mailPrimaryAddress,
                    },
                )

                imap = essential.mail.ImapMail()
                imap.get_connection(mailHomeServer, mailPrimaryAddress, password)

                # no subject tag test
                print('*** check default behavior, no subject tag')
                subject = 'my subject %s' % time.time()
                essential.mail.send_mail(recipients=mailPrimaryAddress, gtube=True, subject=subject)
                for _i in range(60):
                    msg = imap.get_mails(filter='(SUBJECT "%s")' % subject, mailbox=spam_folder)
                    time.sleep(1)
                    if msg:
                        break
                if len(msg) != 1:
                    utils.fail('Test 1: got %d mails with subject: %s' % (len(msg), subject))
                print('%s == %s ?' % (subject, msg[0]['Subject']))
                if subject != msg[0]['Subject']:
                    utils.fail('Test 1: received subject "%s" differs from sent subject "%s"' % (msg[0]['Subject'], subject))
                else:
                    print('*** SUBJECT IS CORRECT')

                # subject tag test
                print('*** check if subject is modified if mail/antispam/headertag is set')
                tag = '*** UCS_TEST ***'
                essential.mail.activate_spam_header_tag(tag)
                essential.mail.reload_amavis_postfix()
                subject = 'my subject %s' % time.time()
                wanted = tag + subject
                essential.mail.send_mail(recipients=mailPrimaryAddress, gtube=True, subject=subject)
                for _i in range(60):
                    msg = imap.get_mails(filter='(SUBJECT "%s")' % subject, mailbox=spam_folder)
                    time.sleep(1)
                    if msg:
                        break
                if len(msg) != 1:
                    utils.fail('Test 2: got %d mails with subject: %s' % (len(msg), subject))
                print('%s == %s ?' % (wanted, msg[0]['Subject']))
                if wanted != msg[0]['Subject']:
                    utils.fail('Test 2: received subject "%s" differs from what we want "%s"' % (msg[0]['Subject'], wanted))
                else:
                    print('*** SUBJECT IS CORRECT')
        finally:
            essential.mail.reload_amavis_postfix()


if __name__ == '__main__':
    main()
