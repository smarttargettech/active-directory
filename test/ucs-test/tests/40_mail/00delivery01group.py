#!/usr/share/ucs-test/runner python3
## desc: Basic group email delivery
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server, univention-mail-postfix]
## bugs: [23527]

#################
#  Information  #
#################
# This script creates three users and gives each user the same alternative eMail address.
# It then sends an eMail to the address and checks if all three user received it.
#################

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import file_search_mail, send_mail


def main():
    TIMEOUT = 60
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()
    with udm_test.UCSTestUDM() as udm:
        domain = ucr.get('domainname')
        group_mail = 'g%s@%s' % (uts.random_string(), domain)
        mails = []
        for _i in range(3):
            usermail = '%s@%s' % (uts.random_name(), domain)
            udm.create_user(
                set={
                    'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                    'mailAlternativeAddress': group_mail,
                    'mailPrimaryAddress': usermail,
                },
            )
            mails.append(usermail)

        token = str(time.time())
        send_mail(recipients=group_mail, msg=token, idstring=token, subject='Test Group Send')

        failed_addresses = ['DUMMY']
        while TIMEOUT > 0 and failed_addresses:
            TIMEOUT -= 1
            failed_addresses = []
            for mail in mails:
                if not file_search_mail(tokenlist=[token], mail_address=mail):
                    failed_addresses.append(mail)
            time.sleep(1)
        for address in failed_addresses:
            utils.fail('mail sent to group address %r was not delivered to %r' % (group_mail, address))


if __name__ == '__main__':
    main()
