#!/usr/share/ucs-test/runner /usr/share/ucs-test/playwright
## desc: Tests the Self Service Subpages
## tags: [apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-self-service

import time

import pytest
from playwright.sync_api import Page, expect

from univention.testing import utils


LINK_HASHES = ['profile', 'createaccount', 'verifyaccount', 'passwordchange', 'passwordforgotten', 'protectaccount']


def get_visible_selfservice_links(page: Page):
    links = []
    for link in page.locator(".portal-tile__root-element").get_by_role('link').all():
        links.append(link.get_attribute('href').rsplit('#', 1)[1])
    return sorted(links)


def assert_link_hashes(links, without):
    wanted_hashes = [link_hash for link_hash in LINK_HASHES if link_hash not in without]
    assert len(links) == len(wanted_hashes)
    for link_hash in wanted_hashes:
        assert f'/selfservice/{link_hash}' in links


def goto_selfservice(page: Page, login=False):
    if login:
        page.goto("http://localhost/univention/login/?location=/univention/selfservice/")
        page.get_by_label("Username", exact=True).fill("Administrator")
        page.get_by_label("Password", exact=True).fill("univention")
        page.get_by_role("button", name="Login").click()
    else:
        page.goto('http://localhost/univention/selfservice/')
    time.sleep(3)


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


def test_all_links(page: Page):
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['verifyaccount', 'createaccount', 'passwordchange'])


def test_all_links_login(page: Page):
    goto_selfservice(page, login=True)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['verifyaccount', 'createaccount', "passwordforgotten"])


def test_disabled_protectaccount(page: Page, ucr):
    ucr.handler_set(['umc/self-service/protect-account/backend/enabled=false'])
    utils.wait_for_replication()
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['protectaccount', 'verifyaccount', 'createaccount', 'passwordchange'])


def test_disabled_passwordforgotten(page: Page, ucr):
    ucr.handler_set(['umc/self-service/passwordreset/backend/enabled=false'])
    utils.wait_for_replication()
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['passwordforgotten', 'verifyaccount', 'createaccount', 'passwordchange'])


def test_disabled_passwordchange(page: Page, ucr):
    ucr.handler_set(['umc/self-service/passwordchange/frontend/enabled=false'])
    utils.wait_for_replication()
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['passwordchange', 'verifyaccount', 'createaccount'])


def test_disabled_profiledata(page: Page, ucr):
    ucr.handler_set(['umc/self-service/profiledata/enabled=false'])
    utils.wait_for_replication()
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['profile', 'verifyaccount', 'createaccount', 'passwordchange'])


def test_disabled_accountregistration(page: Page, ucr):
    ucr.handler_set(['umc/self-service/account-registration/backend/enabled=true'])
    utils.wait_for_replication()
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['verifyaccount', 'passwordchange'])


def test_disabled_accountverification(page: Page, ucr):
    ucr.handler_set(['umc/self-service/account-verification/backend/enabled=true'])
    utils.wait_for_replication()
    goto_selfservice(page)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['createaccount', 'passwordchange'])


def test_login_disabled_passwordchange(page: Page, ucr):
    ucr.handler_set(['umc/self-service/passwordchange/frontend/enabled=false'])
    goto_selfservice(page, login=True)
    links = get_visible_selfservice_links(page)
    assert_link_hashes(links, without=['verifyaccount', 'createaccount', 'passwordforgotten'])
