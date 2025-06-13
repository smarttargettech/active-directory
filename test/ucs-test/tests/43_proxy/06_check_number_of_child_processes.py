#!/usr/share/ucs-test/runner python3
## desc: check number of child processes
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave]
## tags: [apptest]
## exposure: dangerous
## packages: [univention-squid]
## bugs: [40095]

import random
import time

import psutil
from atexit import register

import univention.testing.ucr as ucr_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.simplesquid import SimpleSquid


def main():
    squid = SimpleSquid()
    with ucr_test.UCSTestConfigRegistry() as ucr:
        # throw dice several times
        expected = {
            'squid_ldap_auth': random.randint(3, 30),
            'squid_ldap_ntlm': random.randint(3, 30),
            'squid_kerb_auth': random.randint(3, 30),
            'squidGuard': random.randint(3, 30),
        }

        # set up squid
        handler_set([
            'squid/basicauth=yes',
            'squid/ntlmauth=yes',
            'squid/krb5auth=yes',
            'squid/basicauth/children=%d' % (expected['squid_ldap_auth'],),
            'squid/ntlmauth/children=%d' % (expected['squid_ldap_ntlm'],),
            'squid/krb5auth/children=%d' % (expected['squid_kerb_auth'],),
            'squid/rewrite/children=%d' % (expected['squidGuard'],),
        ])
        squid.restart()
        register(squid.restart)
        time.sleep(3)

        # cou
        result = {
            'squid_ldap_auth': 0,
            'squid_ldap_ntlm': 0,
            'squid_kerb_auth': 0,
        }
        if ucr.get('squid/redirect') == 'squidguard':
            result['squidGuard'] = 0

        MAX_ATTEMPTS = 6
        for attempt in range(MAX_ATTEMPTS):
            print('Attempt %d of %d:' % (attempt + 1, MAX_ATTEMPTS))
            time.sleep(2**attempt)  # wait 1, 2, 4, 8, 16, 32 seconds
            ok = True
            for process in psutil.process_iter():
                if process.name() in result and not process.get_children():  # helper processes do not have child processes
                    result[process.name] += 1

            for key, value in result.items():
                if expected[key] != value:
                    print('ERROR: Found process %r %d times but expected %d times.' % (key, value, expected[key]))
                else:
                    print('Found process %r %d times.' % (key, value))
            if ok:
                break
        else:
            utils.fail('After %d attempts, there was still an unexpected number of processes running.' % (MAX_ATTEMPTS,))


if __name__ == '__main__':
    main()
