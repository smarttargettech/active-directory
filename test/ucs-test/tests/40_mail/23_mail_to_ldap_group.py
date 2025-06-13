#!/usr/share/ucs-test/runner python3
## desc: Mails to ldap group
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import time

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import check_delivery, send_mail


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        if ucr.is_true('mail/dovecot'):
            univention.config_registry.handler_set([
                'mail/dovecot/logging/auth_debug=yes',
                'mail/dovecot/logging/auth_debug_passwords=yes', 'mail/dovecot/logging/auth_verbose=yes',
                'mail/dovecot/logging/auth_verbose_passwords=yes', 'mail/dovecot/logging/mail_debug=yes'])
            logfiles = ['/var/log/mail.log', '/var/log/auth.log', '/var/log/univention/listener.log', '/var/log/dovecot.log']
            autocallcmd = ['doveadm', 'log', 'reopen']
        else:
            logfiles = ['/var/log/mail.log', '/var/log/auth.log', '/var/log/univention/listener.log']
            autocallcmd = ['true']
        with utils.FollowLogfile(logfiles=logfiles):
            with utils.AutoCallCommand(enter_cmd=autocallcmd, exit_cmd=autocallcmd):
                with udm_test.UCSTestUDM() as udm:
                    domain = ucr.get('domainname')
                    password = 'univention'
                    mails_list = []
                    users_list = []
                    for i in range(4):
                        mail = '%s@%s' % (uts.random_name(), domain)
                        user_dn, _username = udm.create_user(
                            set={
                                'password': password,
                                'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                                'mailPrimaryAddress': mail if i > 0 else '',
                            },
                            check_for_drs_replication=True,
                        )
                        mails_list.append(mail)
                        users_list.append(user_dn)
                    group_name = uts.random_name()
                    group_mail = '%s@%s' % (group_name, domain)
                    print('Users List = ', users_list)
                    group_dn = udm.create_object(
                        'groups/group',
                        set={
                            'name': group_name,
                            'mailAddress': group_mail,
                            'users': users_list[0],
                        },
                        position='cn=groups,%s' % ucr.get('ldap/base'),
                        check_for_drs_replication=True,
                    )
                    udm.modify_object(
                        'groups/group',
                        dn=group_dn,
                        append={
                            'users': users_list[1:3],
                        },
                        check_for_drs_replication=True,
                    )
                    token = str(time.time())
                    send_mail(recipients=group_mail, msg=token, tls=True, username=mail, password=password)
                    for i, mail in enumerate(mails_list):
                        should_be_delivered = False
                        if i in [1, 2]:
                            should_be_delivered = True
                        print(40 * '-', '\nUser Nr.: %d, should be delivered = %r\n' % (i, should_be_delivered))
                        check_delivery(token, mail, should_be_delivered)

                    udm.modify_object(
                        'groups/group',
                        dn=group_dn,
                        append={
                            'users': [users_list[3]],
                        },
                        check_for_drs_replication=True,
                    )
                    send_mail(recipients=group_mail, msg=token, tls=True, username=mail, password=password)
                    for i, mail in enumerate(mails_list):
                        should_be_delivered = True
                        if i == 0:
                            should_be_delivered = False
                        print(40 * '-', '\nUser Nr.: %d, should be delivered = %r\n' % (i, should_be_delivered))
                        check_delivery(token, mail, should_be_delivered)

                    udm.modify_object(
                        'users/user',
                        dn=users_list[0],
                        set={
                            'mailPrimaryAddress': mails_list[0],
                        },
                        check_for_drs_replication=True,
                    )
                    send_mail(recipients=group_mail, msg=token, tls=True, username=mail, password=password)
                    for i, mail in enumerate(mails_list):
                        should_be_delivered = True
                        print(40 * '-', '\nUser Nr.: %d, should be delivered = %r\n' % (i, should_be_delivered))
                        check_delivery(token, mail, should_be_delivered)


if __name__ == '__main__':
    main()
