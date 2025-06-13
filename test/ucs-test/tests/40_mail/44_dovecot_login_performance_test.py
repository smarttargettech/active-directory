#!/usr/share/ucs-test/runner python3
## desc: Test logon time with many groups in LDAP
## tags: [producttest]
## timeout: 0
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-directory-manager-tools

import imaplib
import random
import time

import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.ucs_samba import wait_for_drs_replication

from essential.mail import random_email


timeout = 10
MAX_USER = 100
MAX_GRP = 8000
MAX_TESTS = 50


class Bunch:

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __repr__(self):
        return repr(self.__dict__)


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            fqdn = '%(hostname)s.%(domainname)s' % ucr
            grplist = []
            userlist = []
            for i in range(MAX_USER):
                user_addr = random_email()
                user_dn, user_name = udm.create_user(set={
                    'mailHomeServer': fqdn,
                    'mailPrimaryAddress': user_addr,
                }, wait_for_replication=False, check_for_drs_replication=False)
                userlist.append(Bunch(dn=user_dn, name=user_name, addr=user_addr))
                if i % 10 == 0:
                    print('Already created %d users' % (i + 1,))
            utils.wait_for_replication()
            for i in range(MAX_GRP):
                dn, grpname = udm.create_group(
                    set={'users': userlist[random.randint(0, MAX_USER - 1)].dn},
                    wait_for_replication=False, check_for_drs_replication=False)
                grplist.append(Bunch(dn=dn, name=grpname))
                if i % 10 == 0:
                    print('Already created %d groups' % (i + 1,))
            utils.wait_for_replication()
            if utils.package_installed('univention-samba4'):
                wait_for_drs_replication('cn=%s' % dn.partition(",")[0].rpartition("=")[-1])
            try:
                start_time = time.monotonic()
                for i in range(MAX_TESTS):
                    print('Test %d' % (i, ))
                    M = imaplib.IMAP4_SSL(host='localhost')  # establish connection
                    M.login(userlist[random.randint(0, MAX_USER - 1)].addr, 'univention')  # use random users
            finally:
                end_time = time.monotonic()
                print('IMAP login for %d random users took %f seconds ==> %f per login' % (
                    i + 1,
                    end_time - start_time,
                    (end_time - start_time) / float(i + 1),
                ))


if __name__ == '__main__':
    main()
