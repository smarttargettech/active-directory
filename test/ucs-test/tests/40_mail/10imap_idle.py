#!/usr/share/ucs-test/runner python3
## desc: Imap idle test
## tags: [mail]
## exposure: dangerous
## packages: [univention-mail-server]
## bugs: [36907]

import imaplib
import os
import signal
import sys
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import send_mail


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:

        timeout = 30
        password = uts.random_string()
        udm = udm_test.UCSTestUDM()
        mailPrimaryAddress = '%s@%s' % (uts.random_name(), ucr.get('domainname'))
        mailHomeServer = '%(hostname)s.%(domainname)s' % ucr

        udm.create_user(
            password=password,
            set={
                'mailHomeServer': mailHomeServer,
                'mailPrimaryAddress': mailPrimaryAddress,
            },
        )

        newpid = os.fork()
        if newpid == 0:
            print('idle-client: starting imap idle')
            c = imaplib.IMAP4_SSL(mailHomeServer)
            c.login(mailPrimaryAddress, password)
            c.select('INBOX', readonly=True)
            c.send(b"%s IDLE\r\n" % (c._new_tag()))
            while True:
                line = c.readline().decode('UTF-8').strip()
                print('idle-client: got line %s' % line)
                if line.endswith('EXISTS'):
                    print('idle-client: OK, we are good')
                    sys.exit(0)
            sys.exit(1)
        else:
            time.sleep(3)
            pid = None
            status = None
            try:
                print('observer: sending mail')
                send_mail(recipients=mailPrimaryAddress)
                # wait for child
                for i in range(timeout):
                    pid, status = os.waitpid(newpid, os.WNOHANG)
                    print('observer: checking status -> pid:%d status:%d' % (pid, os.WEXITSTATUS(status)))
                    if pid:
                        if os.WEXITSTATUS(status) == 0:
                            print('observer: child finished successfully')
                        else:
                            print('observer: child failed with %d' % os.WEXITSTATUS(status))
                        break
                    else:
                        print('observer: waiting for child (timeout=%s)' % i)
                        time.sleep(1)
            finally:
                udm.cleanup()
                if not pid:
                    print("observer: timeout!, killing child")
                    os.kill(newpid, signal.SIGKILL)
                    utils.fail('imap idle check failed with timeout (%ds)' % timeout)
                elif status and os.WEXITSTATUS(status) != 0:
                    print('observer: child failed with %d' % os.WEXITSTATUS(status))
                    utils.fail('imap idle client check failed with %d') % os.WEXITSTATUS(status)


if __name__ == '__main__':
    main()
