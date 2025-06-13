#!/usr/share/ucs-test/runner python3
## desc: http-proxy-basic-auth-encoding-check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## exposure: dangerous
## packages: [univention-squid]
## bugs: [34154]

import base64
import subprocess

import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set, handler_unset
from univention.testing import utils

from essential.simplesquid import SimpleSquid


def get_basic_auth_header(base64_encoded_creds):
    return f'Proxy-Authorization: Basic {base64_encoded_creds}'


def get_base64_encoded_creds(username, password, encoding):
    return base64.b64encode(f'{username}:{password}'.encode(encoding)).decode('ASCII')


def check_proxy(user, encoding):
    print(f'Now checking encoding: {encoding}')
    print('Username: {}, Password: {}'.format(user['username'], user['password']))
    url = 'http://www.univention.de/'
    try:
        credentials = get_base64_encoded_creds(user['username'], user['password'], encoding)
    except UnicodeEncodeError:
        print("Warning can't encode username or passwrd")
        print("IE would just send a question mark. Nothing we can do. Pass this test.")
        print('##########################')
        return
    basic_auth_header = get_basic_auth_header(credentials)
    print(f'Using credentials: {credentials}')
    subprocess.check_call([
        'curl',
        '--fail',
        '--silent',
        '--output',
        '/dev/null',
        '--proxy',
        'localhost:3128',
        '--header',
        basic_auth_header,
        '--url',
        url,
    ])
    print('Success')
    print('##########################')


def main():
    squid = SimpleSquid()
    with ucr_test.UCSTestConfigRegistry(), udm_test.UCSTestUDM() as udm:

        handler_set(['squid/basicauth=yes'])
        handler_unset(['squid/ntlmauth'])
        squid.reconfigure()

        users = [
            {'username': 'umlaut', 'password': 'ünivention'},
            {'username': 'snowman', 'password': '☃univention'},
        ]
        encodings = ['utf8', 'iso-8859-1']

        for user in users:
            udm.create_user(username=user['username'], password=user['password'])
            for encoding in encodings:
                check_proxy(user, encoding)
        fail_user = {'username': 'umlaut', 'password': 'univention'}
        print('Now checking wrong password')
        for encoding in encodings:
            try:
                check_proxy(fail_user, encoding)
                utils.fail('Proxy login possible with wrong password!')
            except subprocess.CalledProcessError:
                # Login at proxy failed as expected
                pass
        print('Success: No login possible with wrong password')
        print('##########################')

    squid.reconfigure()


if __name__ == '__main__':
    main()
