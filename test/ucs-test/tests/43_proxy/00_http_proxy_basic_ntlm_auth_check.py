#!/usr/share/ucs-test/runner python3
## desc: http-proxy-basic-ntlm-auth-check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest]
## exposure: dangerous
## packages: [univention-squid]

import itertools

import pycurl

import univention.testing.ucr as ucr_test
from univention.config_registry import handler_set, handler_unset
from univention.testing import utils

from essential.simplecurl import SimpleCurl
from essential.simplesquid import SimpleSquid


def checkAuths(host, passwd, url, basic_ntlm, expect_wrong_password):
    basic, ntlm = basic_ntlm
    # in case all auth are disabled, all return 200
    http_basic, http_ntlm = (200, 200)
    if basic or ntlm:
        http_basic = 200 if (basic and not expect_wrong_password) else 407
        http_ntlm = 200 if (ntlm and not expect_wrong_password) else 407
    checkBasic(host, passwd, url, http_basic)
    checkNTLM(host, passwd, url, http_ntlm)


def checkBasic(host, passwd, url, http_code):
    print('Performing Basic proxy auth check')
    curl = SimpleCurl(proxy=host, password=passwd, auth=pycurl.HTTPAUTH_BASIC)
    result = curl.response(url)
    if http_code != result:
        utils.fail('Basic proxy auth check failed, http_code = %r, expected = %r' % (result, http_code))


def checkNTLM(host, passwd, url, http_code):
    print('Performing NTLM proxy auth check')
    curl = SimpleCurl(proxy=host, password=passwd, auth=pycurl.HTTPAUTH_NTLM)
    result = curl.response(url)
    if http_code != result:
        utils.fail('NTLM proxy auth check failed, http_code = %r, expected = %r' % (result, http_code))


def setAuthVariables(squid, basic_ntlm):
    """set ucr variables according to the auth states, and reconfigure Squid"""
    basic, ntlm = basic_ntlm
    if basic:
        handler_set(['squid/basicauth=yes'])
    else:
        handler_unset(['squid/basicauth'])
    if ntlm:
        handler_set(['squid/ntlmauth=yes'])
    else:
        handler_unset(['squid/ntlmauth'])
    squid.reconfigure()


def printHeader(state, passwd, expect_wrong_password):
    print('-' * 40)
    print('(Basic, NTLM) = %s' % (state,))
    print('Password used: %s, expect_wrong_password: %s' % (
        passwd, expect_wrong_password))


def main():
    squid = SimpleSquid()
    with ucr_test.UCSTestConfigRegistry() as ucr:
        handler_unset(['squid/krb5auth'])
        # url = ucr.get('proxy/filter/redirecttarget')
        url = 'http://www.univention.de/'
        host = '%(hostname)s.%(domainname)s' % ucr

        # list of tuples (passwd, expect_wrong_password) used in the test
        account = utils.UCSTestDomainAdminCredentials()
        passwords = [
            (account.bindpw, False),
            ('wrong_passwd', True),
        ]

        # Generate all the possibilities for the auth states
        # [(0, 0), (0, 1), (1, 0), (1, 1)]
        authStates = list(itertools.product([0, 1], repeat=2))

        for passwd, expect_wrong_password in passwords:
            for state in authStates:
                printHeader(state, passwd, expect_wrong_password)

                # set ucr variables according to the auth states
                setAuthVariables(squid, state)

                # Perform the checks
                checkAuths(host, passwd, url, state, expect_wrong_password)
    squid.reconfigure()


if __name__ == '__main__':
    main()
