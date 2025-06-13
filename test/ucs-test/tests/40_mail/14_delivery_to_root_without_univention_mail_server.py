#!/usr/share/ucs-test/runner python3
## desc: Delivery to root without univention mail server
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-postfix
import time

import univention.testing.ucr as ucr_test
from univention.config_registry import handler_set

from essential.mail import check_delivery, send_mail


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        fqdn = '%(hostname)s.%(domainname)s' % ucr
        handler_set(['mail/alias/root=systemmail@%s' % fqdn])
        for recipient in ['root', 'root@localhost', 'root@%s' % fqdn]:
            token = str(time.time())
            send_mail(recipients=recipient, msg=token, tls=True)
            check_delivery(token, recipient, True)


if __name__ == '__main__':
    main()
