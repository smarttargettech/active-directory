#!/usr/share/ucs-test/runner python3
## desc: Basic email delivery to root
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server, univention-mail-postfix]
## bugs: [23527]

#################
#  Information  #
#################
# This script creates a user and then sends an eMail to root.
# It then set the user as receiver (alias [mail/alias/root]) for the eMail to root,
# then sends an eMail to root, and resets "mail/alias/root".
# Finally it checks that both eMail have arrived and deletes the user.
#################

import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import mail_delivered, send_mail


def reload_postfix():
    print('** Reloading aliases and postfix')
    for cmd in (['newaliases'], ['postfix', 'reload']):
        subprocess.Popen(cmd, stderr=open('/dev/null', 'w')).communicate()
    time.sleep(5)


def main():
    TIMEOUT = 60
    with udm_test.UCSTestUDM() as udm:
        try:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                domain = ucr.get('domainname')
                host = ucr.get('hostname')
                handler_set([f'mail/alias/root=systemmail@{host}.{domain}'])
                reload_postfix()

                mail = f'{uts.random_name()}@{domain}'
                _userdn, _username = udm.create_user(
                    set={
                        'mailHomeServer': f'{host}.{domain}',
                        'mailPrimaryAddress': mail,
                    },
                )
                token = str(time.time())
                delivery_OK = False
                send_mail(recipients='root', msg=token, idstring=token, subject='Normal')
                for _i in range(TIMEOUT):
                    if mail_delivered(token, check_root=True):
                        delivery_OK = True
                        break
                    else:
                        print("Mail sent to root has not been delivered yet")
                        time.sleep(1)
                if not delivery_OK:
                    utils.fail('Mail sent to root was not delivered')

                handler_set(['mail/alias/root=%s' % mail])
                reload_postfix()

                token = str(time.time())
                delivery_OK = False
                send_mail(recipients='root', msg=token, idstring=token, subject='Alias')
                for _i in range(TIMEOUT):
                    if mail_delivered(token, mail_address=mail, check_root=False):
                        delivery_OK = True
                        break
                    else:
                        print("Mail sent to %s has not been delivered yet" % mail)
                        time.sleep(1)
                if not delivery_OK:
                    utils.fail('Mail sent to %s was not delivered' % mail)
        finally:
            reload_postfix()


if __name__ == '__main__':
    main()
