#!/usr/share/ucs-test/runner python3
## desc: Basic spam email delivery
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-directory-manager-tools
##  - univention-antivir-mail
## bugs: [23527]

#################
#  Information  #
#################
# This script test the spam detection by creating a user, sending a normal
# eMail, sending a spam eMail and sending a spam eMail with the spam filter
# turned off. It then checks if the eMails are in the correct folder and
# are tagged as spam (or not).
#################

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.decorators import WaitForNonzeroResultOrTimeout

from essential.mail import (
    activate_spam_detection, deactivate_spam_detection, file_search_mail, get_spam_folder_name, reload_amavis_postfix,
    send_mail,
)


def main():
    TIMEOUT = 60
    with udm_test.UCSTestUDM() as udm:
        try:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                domain = ucr.get('domainname')
                mail = 'spam%stest@%s' % (uts.random_string(), domain)
                _userdn, _username = udm.create_user(
                    set={
                        'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                        'mailPrimaryAddress': mail,
                    },
                )

                activate_spam_detection()
                reload_amavis_postfix()

                spam_folder = get_spam_folder_name()
                file_search_mail_with_waiting_loop = WaitForNonzeroResultOrTimeout(file_search_mail, TIMEOUT)

                token1 = str(time.time())
                send_mail(recipients=mail, msg=token1, idstring=token1, subject='Normal')
                if not file_search_mail_with_waiting_loop(tokenlist=[token1, 'X-Spam-Flag: NO'], mail_address=mail):
                    utils.fail('Mail sent with token = %r to %s was not delivered' % (token1, mail))
                print('*** Mail without spam successfully delivered')

                token2 = str(time.time())
                send_mail(recipients=mail, msg=token2, gtube=True, subject='Filter')
                if not file_search_mail_with_waiting_loop(tokenlist=[token2, 'X-Spam-Flag: YES'], mail_address=mail, folder=spam_folder):
                    utils.fail('Spam sent with token = %r to %s sent with filter, was not delivered to spam folder, or does not have a spam flag' % (token2, mail))
                print('*** Mail with spam successfully delivered and detected as SPAM')

                deactivate_spam_detection()
                reload_amavis_postfix()

                token3 = str(time.time())
                send_mail(recipients=mail, msg=token3, gtube=True, subject='No Filter')
                if not file_search_mail_with_waiting_loop(tokenlist=[token3], mail_address=mail):
                    utils.fail('Spam sent with token = %r to %s sent without filter, was not delivered to main mail folder' % (token3, mail))
                print('*** Mail with spam successfully delivered while spam detection is turned off')
        finally:
            reload_amavis_postfix()


if __name__ == '__main__':
    main()
