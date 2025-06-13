#!/usr/share/ucs-test/runner python3
## desc: Basic email delivery
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server, univention-config, univention-directory-manager-tools]
## bugs: [23527, 35924]

#################
#  Information  #
#################
# This script tests the capability of the mail system to deliver mails to
# recpients with special mail addresses and to local users, thereby also
# testing the basic function of the mail system.
# For every mail address one user is created and deleted at the end of
# this script.
#################

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import file_search_mail, send_mail


TIMEOUT = 120


class Tester:
    def __init__(self):
        self.udm = udm_test.UCSTestUDM()
        self.ucr = ucr_test.UCSTestConfigRegistry()

    def __enter__(self):
        self.udm.__enter__()
        self.ucr.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.udm.__exit__(exc_type, exc_value, traceback)
        self.ucr.__exit__(exc_type, exc_value, traceback)

    def test(self):
        mailsToTest, users = self.create_users_and_mail_addresses()
        print('The mail addresses, that will be tested are: %s' % (mailsToTest,))

        test_cases1 = self.mail_sending_test_1(mailsToTest)
        test_cases2 = self.mail_sending_test_2(users)
        test_cases3 = self.mail_sending_test_3_tls(users)

        self.wait_for_delivery(test_cases1, test_cases2, test_cases3)
        self.fail_if_any_mail_is_undelivered(test_cases1, test_cases2, test_cases3)

    def create_users_and_mail_addresses(self):
        mailsToTest = []
        users = []
        domain = self.ucr.get('domainname')
        mails = [
            'BIG%ssmall@%s' % (uts.random_string(), domain),
            '%s.t.o.c@%s' % (uts.random_string(), domain),
            'un_sc%s@%s' % (uts.random_string(), domain),
            '1fo%so2bar3@%s' % (uts.random_string(), domain),
        ]
        for mail in mails:
            _userdn, username = self.udm.create_user(
                set={
                    'mailHomeServer': '%s.%s' % (self.ucr.get('hostname'), domain),
                    'mailPrimaryAddress': mail,
                },
            )

            users.append(username)
            mailsToTest.extend([mail, mail.upper(), mail.lower()])
        return mailsToTest, users

    def mail_sending_test_1(self, mailsToTest):
        test_cases = []
        for mail in mailsToTest:
            token = str(time.time())
            test_cases.append([token, mail, False])
            print('\nTOKEN = %s\n' % token)
            send_mail(recipients=mail, msg=token, idstring=token, subject='Test')
        return test_cases

    def mail_sending_test_2(self, users):
        test_cases = []
        for user in users:
            token = str(time.time())
            test_cases.append([token, user, False])
            print('\nTOKEN = %s\n' % token)
            send_mail(recipients=user, msg=token, subject='Test')
        return test_cases

    def mail_sending_test_3_tls(self, users):
        test_cases = []
        for user in users:
            token = str(time.time())
            test_cases.append([token, user, False])
            print('\nTOKEN = %s\n' % token)
            send_mail(recipients=user, msg=token, subject='TestTLS', tls=True)
        return test_cases

    def wait_for_delivery(self, test_cases1, test_cases2, test_cases3):
        print("\nWaiting up to %d seconds for delivering mails...\n" % (TIMEOUT, ))
        for timeout in range(TIMEOUT, 0, -1):
            print('Waiting up to %d seconds' % (timeout,))
            all_found = True
            for i, (token, mail, _found) in enumerate(test_cases1):
                if file_search_mail(tokenlist=[token], mail_address=mail):
                    test_cases1[i][2] = True
                else:
                    all_found = False
            for i, (token, user, _found) in enumerate(test_cases2):
                if file_search_mail(tokenlist=[token], user=user):
                    test_cases2[i][2] = True
                else:
                    all_found = False
            for i, (token, user, _found) in enumerate(test_cases3):
                if file_search_mail(tokenlist=[token], user=user):
                    test_cases3[i][2] = True
                else:
                    all_found = False
            if not all_found:
                time.sleep(1)
            else:
                print('All mails have successfully been delivered.')
                break

    def fail_if_any_mail_is_undelivered(self, test_cases1, test_cases2, test_cases3):
        for token, mail, found in test_cases1:
            if not found:
                utils.fail('Mail sent to %r with token %r was not delivered' % (mail, token))
        for token, user, found in test_cases2:
            if not found:
                utils.fail('Mail sent with token = %r, to %s was not delivered' % (token, user))
        for token, user, found in test_cases3:
            if not found:
                utils.fail('Mail sent with token = %r, to %s was not delivered (TLS used)' % (token, user))


if __name__ == '__main__':
    with Tester() as tester:
        tester.test()
