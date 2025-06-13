#!/usr/share/ucs-test/runner pytest-3 -s -vv
## desc: Tests the Univention Self Service
## tags: [apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-self-service
##   - univention-self-service-passwordreset-umc

import subprocess
import time

import pytest
from test_self_service import self_service_user

import univention.lib.umc
from univention.testing.strings import random_username


@pytest.fixture(scope='class', autouse=True)
def close_all_processes():
    """force all module processes to close"""
    yield
    subprocess.call(['systemctl', 'start', 'postgresql'])


def test_reset_via_email(ucr):
    reset_mail_address = f'{random_username()}@{random_username()}'
    with self_service_user(mailPrimaryAddress=reset_mail_address) as user:
        email = 'foo@example.com'
        mobile = '+0176123456'
        user.set_contact(email=email, mobile=mobile)
        assert user.get_contact().get('email') == email, 'Setting mail address failed'

        email = 'testuser@example.com'
        user.set_contact(email=email)
        assert 'email' in user.get_reset_methods()

        user.send_token('email')

        subprocess.call(['systemctl', 'stop', 'postgresql'])
        time.sleep(0.5)
        with pytest.raises(univention.lib.umc.HTTPError, match=r'psycopg2.OperationalError: (connection to server at .* failed|Verbindung zum Server .* fehlgeschlagen)'):
            # "Connection refused" / "Verbindungsaufbau abgelehnt" and "das Datenbanksystem fährt herunter"
            user.send_token('email')

        subprocess.call(['systemctl', 'start', 'postgresql'])
        time.sleep(0.5)
        user.send_token('email')
