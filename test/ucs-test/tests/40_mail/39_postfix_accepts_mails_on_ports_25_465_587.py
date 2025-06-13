#!/usr/share/ucs-test/runner python3
## desc: Postfix accepts mails on port 25, 465 and 587
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server

import syslog

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import check_delivery, send_mail


def main():
    logfiles = ['/var/log/mail.log']
    with ucr_test.UCSTestConfigRegistry() as ucr, udm_test.UCSTestUDM() as udm, utils.FollowLogfile(logfiles=logfiles):
        domain = ucr.get('domainname')
        mail1 = '%s@%s' % (uts.random_name(), domain)
        password = 'univention'
        _user_dn1, _username1 = udm.create_user(
            set={
                'password': password,
                'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                'mailPrimaryAddress': mail1,
            },
        )
        mail2 = '%s@%s' % (uts.random_name(), domain)
        _user_dn2, _username2 = udm.create_user(
            set={
                'password': password,
                'mailHomeServer': '%s.%s' % (ucr.get('hostname'), domain),
                'mailPrimaryAddress': mail2,
            },
        )

        syslog.openlog(facility=syslog.LOG_MAIL)  # get markers in mail.log in case of error

        smtp_args = {
            25: {"port": 25, "tls": True, "ssl": False, "recipients": mail2, "sender": mail1, "msg": uts.random_name()},
            465: {"port": 465, "tls": False, "ssl": True, "recipients": mail2, "sender": mail1, "msg": uts.random_name()},
            587: {"port": 587, "tls": True, "ssl": False, "recipients": mail2, "sender": mail1, "msg": uts.random_name()},
        }

        for kwargs in smtp_args.values():
            syslog.syslog(syslog.LOG_INFO, 'Sending to port {}.'.format(kwargs['port']))
            send_mail(**kwargs)
            check_delivery(kwargs['msg'], mail2, True)
            print('*** OK: mail delivered through port {}.'.format(kwargs['port']))
            syslog.syslog(syslog.LOG_INFO, 'OK: mail delivered through port {}.'.format(kwargs['port']))


if __name__ == '__main__':
    main()
