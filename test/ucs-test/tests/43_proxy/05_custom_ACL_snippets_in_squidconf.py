#!/usr/share/ucs-test/runner python3
## desc: Custom ACL snippets in squid.conf
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest, SKIP]
## exposure: dangerous
## packages: [univention-squid]

import itertools
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from multiprocessing import Process

import pycurl

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
from univention.config_registry import handler_set, handler_unset
from univention.testing import utils
from univention.testing.network import NetworkRedirector

from essential.simplecurl import SimpleCurl
from essential.simplesquid import SimpleSquid


class TestServer:
    def __init__(self):
        # start http server in a different thread on (127.0.0.1:60025)
        p = Process(target=startHttpServer, kwargs={'port': 60025})
        p.start()
        print(p, p.is_alive())
        self.p = p

    def __enter__(self):
        handler_set(['hosts/static/127.0.100.100=proxy_test1.univention.de proxy_test2.univention.de'])
        return self

    def __exit__(self, *args):
        # Terminating Http server
        self.p.join(5)
        self.p.terminate()
        time.sleep(0.5)
        print('Http server is terminated...\n%r' % self.p.is_alive())
        handler_unset(['hosts/static/127.0.100.100'])


def startHttpServer(host='localhost', port=80):
    """Start a simple Http server in the working directory"""
    HandlerClass = SimpleHTTPRequestHandler
    ServerClass = HTTPServer
    Protocol = "HTTP/1.0"
    server_address = (host, port)

    HandlerClass.protocol_version = Protocol
    httpd = ServerClass(server_address, HandlerClass)

    sa = httpd.socket.getsockname()
    print("Serving HTTP on", sa[0], "port", sa[1], "...")
    httpd.serve_forever()


def perform_test(test_case):
    ((permission, expected_response), acl_type, (value_type, value)) = test_case
    sub_case = []
    opposite_response = 407 if expected_response == 200 else 200

    # Add special cases for each type
    if value_type == 'string':
        used_value = value
        used_value2 = "%s%s%s" % (uts.random_string(2), value, uts.random_string(2))
        if "dstdomain" in acl_type:
            used_value = "http://proxy_test1.univention.de"
            used_value2 = "http://proxy_test2.univention.de/"
        sub_case.extend([
            (permission, expected_response, acl_type, value_type, used_value, value),
            (permission, opposite_response, acl_type, value_type, used_value2, value),
        ])

    if value_type == 'substring':
        used_value = "%s%s%s" % (uts.random_string(2), value, uts.random_string(2))
        if "dstdomain" in acl_type:
            used_value = "http://proxy_test1.univention.de"
        sub_case.append(
            (permission, expected_response, acl_type, value_type, used_value, value),
        )

        used_value = "%s%s%s" % (value[0:2], uts.random_string(3), value[2:5])
        if "dstdomain" in acl_type:
            used_value = "http://proxy_test2.univention.de/"
        sub_case.append(
            (permission, opposite_response, acl_type, value_type, used_value, value),
        )

    if value_type == 'regex':
        used_value = "%s%s" % (value[1:-3], uts.random_string(3))
        if "dstdomain" in acl_type:
            used_value = "http://proxy_test1.univention.de"
        sub_case.append(
            (permission, expected_response, acl_type, value_type, used_value, value),
        )
        used_value = "%s%s%s" % (uts.random_string(1), value[1:-3], uts.random_string(2))
        if "dstdomain" in acl_type:
            used_value = "http://proxy_test2.univention.de/"
        sub_case.append(
            (permission, opposite_response, acl_type, value_type, used_value, value),
        )

    # Add the case sesitivity checks for all cases
    new_cases = list(sub_case)
    for case in sub_case:
        (permission, expected_response, acl_type, value_type, used_value, value) = case

        if acl_type[-1] != 'i' and 'dstdomain' not in acl_type:
            new_cases.extend([
                (permission, opposite_response, acl_type, value_type, used_value.upper(), value),
                (permission, opposite_response, acl_type, value_type, used_value.lower(), value),
            ])
        else:
            new_cases.extend([
                (permission, expected_response, acl_type, value_type, used_value.upper(), value),
                (permission, expected_response, acl_type, value_type, used_value.lower(), value),
            ])

    # The actual test
    do_test(new_cases)


def do_test(test_case):
    for (permission, expected_response, acl_type, value_type, used_value, value) in test_case:
        name = uts.random_name()
        print()
        print('** Name =\t%s' % name)
        print('** Permission =\t%s' % permission)
        print('** Type =\t%s' % acl_type)
        print('** Value Type =\t%s' % value_type)
        print('** Set Value =\t%s' % value)
        print('** Used Value =\t%s' % used_value)
        print('** Expected Response =\t%d' % expected_response)

        set_ucr_variables(name, permission, acl_type, value_type, value)

        ucr = ucr_test.UCSTestConfigRegistry()
        ucr.load()
        auth = None
        if permission == 'deny':
            auth = pycurl.HTTPAUTH_BASIC
        curl = SimpleCurl(proxy=ucr.get('hostname'), auth=auth)
        if 'browser' in acl_type:
            curl = SimpleCurl(proxy=ucr.get('hostname'), auth=auth, user_agent=used_value)

        url = 'http://proxy_test1.univention.de'
        if "dstdomain" in acl_type:
            url = used_value

        if "port" in acl_type:
            url = '127.0.100.100:%d' % used_value

        response = curl.response(url)
        print("Response = %d" % response)
        if response != expected_response:
            utils.fail("Unexpected Response: %d != %d" % (response, expected_response))
        else:
            print(':::: OK ::::')


def set_ucr_variables(name, permission, acl_type, value_type, value):
    squid = SimpleSquid()
    handler_set([
        'squid/acl/%s/%s/%s/%s=%s' % (name, permission, acl_type, value_type, value),
        'squid/basicauth=yes',
    ])

    squid.reconfigure()


def main():
    try:
        permissions = ['allow', 'deny']
        responses = [200, 403]
        value_types = ['string', 'substring', 'regex']

        # Test user-agent variable with random data
        acl_types = ['browser', 'browser-i']
        values = [
            "%s%s%s" % (
                uts.random_string(3),
                uts.random_string(2, numeric=False).upper(),
                uts.random_string(3)),
            "%s%s%s" % (
                uts.random_string(3),
                uts.random_string(2, numeric=False).upper(),
                uts.random_string(3)),
            "%s%s%s%s%s" % (
                '^', uts.random_string(3),
                uts.random_string(2, numeric=False).upper(),
                uts.random_string(3), '.*$'),
        ]
        itertion_length = len(permissions) * len(acl_types) * len(value_types)
        tests = itertools.product(zip(permissions, responses), acl_types, zip(value_types, values))
        for _i in range(itertion_length):
            with ucr_test.UCSTestConfigRegistry():
                perform_test(next(tests))

        # Test dstdomain variable with univention related sites
        acl_types = ['dstdomain', 'dstdomain-i']
        values = [
            'proxy_test1.univention.de',
            'proxy_test1',
            '^proxy_test1.univention.de.*$',
        ]
        tests = itertools.product(zip(permissions, responses), acl_types, zip(value_types, values))
        for _i in range(itertion_length):
            with ucr_test.UCSTestConfigRegistry():
                perform_test(next(tests))

        with ucr_test.UCSTestConfigRegistry():
            do_test([('allow', 200, 'port', 'number', 21, 21)])
        with ucr_test.UCSTestConfigRegistry():
            do_test([('allow', 407, 'port', 'number', 443, 21)])
        with ucr_test.UCSTestConfigRegistry():
            do_test([('deny', 403, 'port', 'number', 21, 21)])
        with ucr_test.UCSTestConfigRegistry():
            do_test([('deny', 200, 'port', 'number', 443, 21)])

    finally:
        squid = SimpleSquid()
        squid.reconfigure()


if __name__ == '__main__':
    with TestServer(), NetworkRedirector() as nethelper:
        nethelper.add_redirection('127.0.100.100', 21, 60025)
        nethelper.add_redirection('127.0.100.100', 80, 60025)
        nethelper.add_redirection('127.0.100.100', 443, 60025)
        main()
