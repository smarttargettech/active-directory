#!/usr/share/ucs-test/runner python3
## desc: Check if UMC is able to return correct IP address
## exposure: dangerous
## packages: [univention-management-console-server]

from http.client import HTTPConnection

from univention.config_registry import ConfigRegistry
from univention.testing import network, utils
from univention.testing.umc import Client


class Client(Client):
    # workaround ssl.CertificateError: hostname '1.2.3.4' doesn't match either of 'master091.$domainname', 'master091'
    ConnectionType = HTTPConnection


def get_ip_address(host, username, password):
    client = Client(host, username, password)
    return client.umc_get('ipaddress').data


def main():
    ucr = ConfigRegistry()
    ucr.load()

    account = utils.UCSTestDomainAdminCredentials()

    with network.NetworkRedirector() as nethelper:
        print('*** Check with different remote addresses')
        for addr2 in ('4.3.2.1', '1.1.1.1', '2.2.2.2'):
            nethelper.add_loop('1.2.3.4', addr2)

            result = get_ip_address('1.2.3.4', account.username, account.bindpw)
            print('Result: %r' % result)
            if addr2 not in result:
                utils.fail(f'UMC webserver is unable to determine correct HTTP client address (expected={addr2!r} result={result!r})')

            nethelper.remove_loop('1.2.3.4', addr2)

        print('*** Check with localhost')
        result = get_ip_address('localhost', account.username, account.bindpw)
        if result:
            utils.fails('Response is expected to be empty')


if __name__ == '__main__':
    main()
