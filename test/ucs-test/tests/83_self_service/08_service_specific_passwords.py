#!/usr/share/ucs-test/runner /usr/share/ucs-test/playwright
## desc: Tests the service specific password creation for radius
## tags: [apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-self-service
##   - univention-radius

import subprocess
import time

import passlib.hash
import pytest
from playwright.sync_api import expect

import univention.admin.uldap
from univention.config_registry import handler_set as hs
from univention.testing import utils
from univention.testing.ucr import UCSTestConfigRegistry


@pytest.fixture(scope='session')
def browser_context_args(browser_context_args):
    expect.set_options(timeout=30 * 1000)
    return {**browser_context_args, 'ignore_https_errors': True, 'locale': 'en-US'}


@pytest.fixture(scope='session')
def browser_type_launch_args(browser_type_launch_args):
    return {
        **browser_type_launch_args,
        'executable_path': '/usr/bin/chromium',
        'args': [
            '--disable-gpu',
        ],
    }


@pytest.fixture(scope="module", autouse=True)
def activate_self_registration():
    with UCSTestConfigRegistry() as ucr:
        hs(['umc/self-service/service-specific-passwords/backend/enabled=true'])
        hs(['radius/use-service-specific-password=true'])
        yield ucr


def radius_auth(username, password):
    subprocess.check_call([
        'radtest',
        '-t',
        'mschap',
        username,
        password,
        '127.0.0.1:18120',
        '0',
        'testing123',
    ])


def get_new_ssp(page, username, ucr):
    page.goto(f'http://{ucr["hostname"]}.{ucr["domainname"]}/univention/portal/#/selfservice/servicespecificpasswords')
    page.reload()
    page.get_by_label("Username", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill("univention")
    page.get_by_role("button", name="Next").click()
    page.get_by_role("button", name="Generate WLAN password").click()
    time.sleep(10)
    print(page.content())
    password = page.locator(".service-specific-passwords__hint").inner_text().split('\n')
    print(password)
    return password[1]


def test_service_specific_password(page, ucr, udm):
    lo = univention.admin.uldap.access(
        host=ucr.get('ldap/master'),
        port=ucr.get('ldap/server/port'),
        base=ucr.get('ldap/base'),
        binddn=ucr.get('tests/domainadmin/account'),
        bindpw=ucr.get('tests/domainadmin/pwd'),
        start_tls=2,
        follow_referral=True,
    )
    # needs to be restarted to be current wrt umc/self-service/service-specific-passwords/backend/enabled=true
    subprocess.call(['service', 'univention-management-console-server', 'restart'])
    time.sleep(10)

    dn, username = udm.create_user(password='univention', username='service-specific-password', networkAccess='1')
    password = get_new_ssp(page, username, ucr)
    utils.wait_for_replication()

    ldap_nt = lo.get(dn).get('univentionRadiusPassword', ['???'])[0]
    nt = passlib.hash.nthash.hash(password).upper().encode('ascii')
    assert ldap_nt == nt
    with pytest.raises(subprocess.CalledProcessError):
        radius_auth(username, 'univention')
    radius_auth(username, password)

    # get another ssp and verify that the old password does not work any more
    new_password = get_new_ssp(page, username, ucr)
    utils.wait_for_replication()
    ldap_nt = lo.get(dn).get('univentionRadiusPassword', ['???'])[0]
    nt = passlib.hash.nthash.hash(new_password).upper().encode('ascii')
    assert ldap_nt == nt
    with pytest.raises(subprocess.CalledProcessError):
        radius_auth(username, password)
    radius_auth(username, new_password)
