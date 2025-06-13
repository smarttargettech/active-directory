#!/usr/share/ucs-test/runner python3
# This test can be used to check the kerberos authentication with squid.
# Note: out of the box this only works on master systems. And check that the join script is executed.
## desc: http-proxy-kerberos-auth-check
## roles: [domaincontroller_master]
## tags: [apptest, SKIP]
## exposure: dangerous
## packages:
## - univention-squid
## - univention-squid-kerberos
## - univention-s4-connector

import subprocess

import pycurl

import univention.testing.ucr as ucr_test
from univention.config_registry import handler_set, handler_unset
from univention.testing import utils

from essential.simplecurl import SimpleCurl
from essential.simplesquid import SimpleSquid


class kerberos_ticket:
    def __init__(self, hostname):
        self.hostname = hostname

    def __enter__(self):
        subprocess.call(['kdestroy'])
        subprocess.check_call(['kinit', '--password-file=/etc/machine.secret', self.hostname + '$'])  # get kerberos ticket

    def __exit__(self, exc_type, exc_value, traceback):
        subprocess.call(['kdestroy'])


def check_no_ticket(host, url):
    print('Check proxy without kerberos ticket...')
    subprocess.call(['kdestroy'])  # delete all active kerberos tickets
    curl = SimpleCurl(proxy=host, password='will_be_ignored', auth=pycurl.HTTPAUTH_GSSNEGOTIATE)
    result = curl.response(url)
    if result != 407:
        utils.fail('Kerberos proxy auth check failed, http_code = %r, expected = %r' % (result, '407'))
    print('Success: Proxy does not work without kerberos ticket')


def check_with_ticket(host, url, hostname):
    print('Check proxy with kerberos ticket...')
    with kerberos_ticket(hostname):
        curl = SimpleCurl(proxy=host, password='will_be_ignored', auth=pycurl.HTTPAUTH_GSSNEGOTIATE)
        result = curl.response(url)
    if result != 200:
        utils.fail('Kerberos proxy auth check failed, http_code = %r, expected = %r' % (result, '200'))
    print('Success: Proxy does work with kerberos ticket')


def main():
    squid = SimpleSquid()
    try:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            url = 'http://www.univention.de/'
            host = '%(hostname)s.%(domainname)s' % ucr
            hostname = '%(hostname)s' % ucr

            handler_set(['squid/krb5auth=yes'])
            handler_unset(['squid/ntlmauth', 'squid/basicauth'])
            squid.reconfigure()
            check_no_ticket(host, url)
            check_with_ticket(host, url, hostname)
    finally:
        squid.reconfigure()  # Reset auth methods


if __name__ == '__main__':
    main()
