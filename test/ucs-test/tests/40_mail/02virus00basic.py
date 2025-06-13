#!/usr/share/ucs-test/runner python3
## desc: Basic virus email delivery
## tags: []
## exposure: dangerous
## packages: [univention-mail-server, univention-config, univention-directory-manager-tools]
## bugs: [23527]

#################
#  Information  #
#################
# This script tests the eMail virus detection by sending viruses
# to a newly created user both with spam detection on and off,
# and then checking that the viruses were filtered and that the
# user and root was warned.
#################

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import deactivate_spam_detection, reload_amavis_postfix, send_mail, virus_detected_and_quarantined


def main():
    TIMEOUT = 60
    with udm_test.UCSTestUDM() as udm:
        try:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                domain = ucr.get('domainname')
                host = ucr.get('hostname')
                handler_set([
                    'mail/alias/root=systemmail@%s.%s' % (
                            host, domain),
                ])
                reload_amavis_postfix()
                mail = 'virus%stest@%s' % (uts.random_string(), domain)
                _userdn, _username = udm.create_user(
                    set={
                        'mailHomeServer': '%s.%s' % (host, domain),
                        'mailPrimaryAddress': mail,
                    },
                )

                token1 = str(time.time())
                send_mail(recipients=mail, msg=token1, virus=True, subject='Filter on')
                time.sleep(5)

                deactivate_spam_detection()
                reload_amavis_postfix()

                token2 = str(time.time())
                send_mail(recipients=mail, msg=token2, virus=True, subject='Filter off')

                while TIMEOUT > 0:
                    print('Waiting up to %d seconds' % (TIMEOUT,))
                    TIMEOUT -= 1
                    if all([virus_detected_and_quarantined(token1, mail_address=mail), virus_detected_and_quarantined(token2, mail_address=mail)]):
                        break
                    time.sleep(1)

                for token in [token1, token2]:
                    if not virus_detected_and_quarantined(token, mail_address=mail):
                        utils.fail('Virus sent with token = %r was not delivered correctly with a warning' % token)

        finally:
            reload_amavis_postfix()


if __name__ == '__main__':
    main()
