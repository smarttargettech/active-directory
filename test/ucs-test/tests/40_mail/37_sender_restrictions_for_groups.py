#!/usr/share/ucs-test/runner python3
## desc: Test sender restrictions for groups
## exposure: dangerous
## packages: [univention-mail-server]

import smtplib
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import restart_postfix, send_mail


def check_sending_mail(sender, recipient, username, password, should_be_accepted):
    token = str(time.time())
    try:
        ret_code = send_mail(recipients=recipient, sender=sender, msg=token, port=587, tls=True, username=username, password=password, debuglevel=0)
        if bool(ret_code) == should_be_accepted:
            utils.fail('Sending should_be_accepted = %r, but return code = %r\n {} means there are no refused recipient' % (should_be_accepted, ret_code))
    except smtplib.SMTPRecipientsRefused as ex:
        if should_be_accepted:
            utils.fail('Mail sent failed with exception: %s' % ex)


def main():
    cmd = ['/etc/init.d/postfix', 'restart']
    with utils.AutoCallCommand(exit_cmd=cmd, stderr=open('/dev/null', 'w')):
        with ucr_test.UCSTestConfigRegistry() as ucr:
            with udm_test.UCSTestUDM() as udm:
                handler_set(['mail/postfix/policy/listfilter=yes', 'mail/postfix/greylisting=no'])
                restart_postfix()
                domain = ucr.get('domainname')
                password = 'univention'
                mails = []
                alts = []
                users = []
                for i in range(5):
                    mail = '%s@%s' % (uts.random_name(), domain)
                    alt = '%s@%s' % (uts.random_name(), domain)
                    user_dn, _username = udm.create_user(
                        set={
                            'password': password,
                            'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                            'mailPrimaryAddress': mail,
                            'mailAlternativeAddress': alt,
                        },
                    )
                    mails.append(mail)
                    alts.append(alt)
                    users.append(user_dn)
                group1_mail = '%s@%s' % (uts.random_name(), domain)
                group1_dn, group1_name = udm.create_group(
                    set={
                        'mailAddress': group1_mail,
                        'users': users[0],
                    },
                )
                group2_mail = '%s@%s' % (uts.random_name(), domain)
                _group2_dn, group2_name = udm.create_group(
                    set={
                        'mailAddress': group2_mail,
                        'users': users[4],
                        'allowedEmailUsers': users[2],
                        'allowedEmailGroups': group1_dn,
                    },
                )

                print("")
                for i in range(5):
                    print("user: %r \t email: %r emailAlt: %r" % (users[i].partition(",")[0], mails[i], alts[i]))
                print("group %r: email: %r users: %r" % (group1_name, group1_mail, mails[0]))
                print("group %r: email: %r users: %r allowedEmailUsers: %r allowedEmailGroups: %r" % (group2_name, group2_mail, mails[4], mails[2], group1_name))

                for sender in ('noreply@univention.de', mails[1], '<>'):
                    print("\n>>> sending mail to user 1 (%s): sender=%s -> allowed" % (mails[1], sender))
                    check_sending_mail(sender, mails[1], mails[1], password, True)

                print("\n>>> sending to unrestricted mail group %r with a null sender -> allowed" % group1_mail)
                check_sending_mail('<>', group1_mail, mails[0], password, True)
                print("\n>>> sending to unrestricted mail group %r with a member posix account -> allowed" % group1_mail)
                check_sending_mail(mails[0], group1_mail, mails[0], password, True)
                print("\n>>> sending to unrestricted mail group %r with a non-member -> allowed" % group1_mail)
                check_sending_mail(mails[1], group1_mail, mails[1], password, True)
                print("\n>>> sending to restricted mail group %r with a null sender -> not allowed" % group2_mail)
                check_sending_mail('<>', group2_mail, mails[4], password, False)
                print("\n>>> sending to restricted mail group %r with a member posix account -> not allowed" % group2_mail)
                check_sending_mail(mails[4], group2_mail, mails[4], password, False)
                print("\n>>> sending to restricted mail group %r with a non-member -> not allowed" % group2_mail)
                check_sending_mail(mails[3], group2_mail, mails[3], password, False)
                print("\n>>> sending to restricted mail group %r with a non-member posix account but as a user in allowedEmailUsers using its mailPrimaryAddress -> allowed" % group2_mail)
                check_sending_mail(mails[2], group2_mail, mails[2], password, True)
                print("\n>>> sending to restricted mail group %r with a non-member posix account but as a user in allowedEmailUsers using its mailAlternativeAddress -> allowed" % group2_mail)
                check_sending_mail(alts[2], group2_mail, mails[2], password, True)
                print("\n>>> sending to restricted mail group %r with a non-member posix account but as a member of a group in allowedEmailGroups using its mailPrimaryAddress -> allowed" % group2_mail)
                check_sending_mail(mails[0], group2_mail, mails[0], password, True)
                print("\n>>> sending to restricted mail group %r with a non-member posix account but as a member of a group in allowedEmailGroups using its mailAlternativeAddress -> allowed" % group2_mail)
                check_sending_mail(alts[0], group2_mail, mails[0], password, True)


if __name__ == '__main__':
    main()
