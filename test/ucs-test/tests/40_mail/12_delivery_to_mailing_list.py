#!/usr/share/ucs-test/runner python3
## desc: Delivery to a mailing list
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set

from essential.mail import check_delivery, send_mail


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            domain = ucr.get('domainname')
            handler_set(['mail/dovecot/mailbox/delete=yes'])
            subprocess.call(['/etc/init.d/dovecot', 'restart'], stderr=open('/dev/null', 'w'))
            host = '%s.%s' % (ucr.get('hostname'), domain)
            password = 'univention'
            mails = []
            for _i in range(2):
                name = uts.random_name()
                usermail = '%s@%s' % (name, domain)
                _userdn, _username = udm.create_user(
                    username=name,
                    set={
                        'password': password,
                        'mailHomeServer': host,
                        'mailPrimaryAddress': usermail,
                    },
                )
                mails.append(usermail)
            list_name = uts.random_name()
            list_mail = '%s@%s' % (list_name, domain)
            udm.create_object(
                'mail/lists',
                members=mails[0],
                set={
                    'name': list_name,
                    'mailAddress': list_mail,
                    'members': mails[1],
                },
                wait_for_drs_replication=True,
                position="cn=mailinglists,cn=mail,{}".format(ucr.get("ldap/base")),
            )
            token = str(time.time())
            send_mail(recipients=list_mail, msg=token, tls=True, username=usermail, password=password)

            for mail in mails:
                check_delivery(token, mail, True)


if __name__ == '__main__':
    main()
