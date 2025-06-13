#!/usr/share/ucs-test/runner python3
## desc: Test mail to nested groups
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test

from essential.mail import check_delivery, send_mail


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            domain = ucr.get('domainname')
            password = 'univention'
            mails_list = []
            users_list = []
            fqdn = '%s.%s' % (ucr.get('hostname'), domain)
            for i in range(3):
                mail = '%s@%s' % (uts.random_name(), domain)
                user_dn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailHomeServer': fqdn,
                        'mailPrimaryAddress': mail,
                    },
                )
                mails_list.append(mail)
                users_list.append(user_dn)
            group1_mail = '%s@%s' % (uts.random_name(), domain)
            group1_dn, _group1_name = udm.create_group(
                set={
                    'mailAddress': group1_mail,
                    'users': users_list[0],
                },
            )
            group2_mail = '%s@%s' % (uts.random_name(), domain)
            group2_dn, _group2_name = udm.create_group(
                set={'mailAddress': group2_mail},
                append={'users': users_list[1:3]},
            )
            group3_mail = '%s@%s' % (uts.random_name(), domain)
            udm.create_group(
                set={'mailAddress': group3_mail},
                append={'nestedGroup': [group1_dn, group2_dn]},
            )

            token = str(time.time())
            send_mail(recipients=group1_mail, msg=token, debuglevel=0)
            for i, mail in enumerate(mails_list):
                should_be_delivered = i == 0
                print((40 * '-', '\nUser Nr.: %d, should be delivered = %r\n' % (i, should_be_delivered)))
                check_delivery(token, mail, should_be_delivered)

            token = str(time.time())
            send_mail(recipients=group2_mail, msg=token, debuglevel=0)
            for i, mail in enumerate(mails_list):
                should_be_delivered = i in [1, 2]
                print((40 * '-', '\nUser Nr.: %d, should be delivered = %r\n' % (i, should_be_delivered)))
                check_delivery(token, mail, should_be_delivered)

            token = str(time.time())
            send_mail(recipients=group3_mail, msg=token, debuglevel=0)
            should_be_delivered = True
            for i, mail in enumerate(mails_list):
                print((40 * '-', '\nUser Nr.: %d, should be delivered = %r\n' % (i, should_be_delivered)))
                check_delivery(token, mail, should_be_delivered)


if __name__ == '__main__':
    main()
