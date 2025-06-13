#!/usr/share/ucs-test/runner python3
## desc: Check if the webserver is responding after sending many unanswered requests
## bugs: [37487]
## versions:
##  4.0-0: found
##  4.0-1: skip
##  4.1-0: fixed
## tags: [SKIP]
## roles:
##  - domaincontroller_master
## packages:
##  - univention-management-console
##  - univention-management-console-frontend
##  - ucs-test-umc-module
## exposure: dangerous


import ssl
import subprocess

import httplib

from univention.management.console.modules.ucstest import joinscript, unjoinscript
from univention.testing import utils
from univention.testing.umc import Client


NUMBER_OF_NOT_RESPONDING_REQUESTS = 100


class AsyncClient(Client):

    def async_request(self, path):
        cookie = '; '.join(['='.join(x) for x in self.cookies.iteritems()])
        headers = dict(self._headers, **{'Cookie': cookie, 'Content-Type': 'application/json'})
        connection = httplib.HTTPSConnection(self.hostname, timeout=10)
        connection.request('POST', '/univention/command/%s' % path, '{}', headers=headers)
        return connection


def main():
    print('Setting up the connections ...')

    print('Sending %d not responding requests' % NUMBER_OF_NOT_RESPONDING_REQUESTS)
    for _request in range(NUMBER_OF_NOT_RESPONDING_REQUESTS):
        AsyncClient.get_test_connection(timeout=10).async_request('ucstest/norespond')

    print('Verfying the webserver still respond to a request ...')
    try:
        assert AsyncClient.get_test_connection(timeout=10).umc_command('ucstest/respond').status == 200
    except ssl.SSLError:
        utils.fail('ERROR: request timed out')
    except AssertionError:
        utils.fail('ERROR: webserver is not responding')
    finally:
        subprocess.Popen(['systemctl', 'restart', 'univention-management-console-server'])


if __name__ == '__main__':
    joinscript()
    try:
        main()
    finally:
        unjoinscript()
