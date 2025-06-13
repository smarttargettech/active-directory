#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: SSO Login at UMC as Service Provider
## tags: [saml]
## join: true
## exposure: dangerous
## packages:
##   - univention-self-service-passwordreset-umc
## tags:
##  - skip_admember

import pytest

import univention.testing.udm as udm_test

import samltest


def test_check_disabled_email_unverified():
    check_login(activated_email=False)


def test_check_disabled_email_verified():
    check_login(activated_email=True)


def test_check_enabled_email_unverified(change_app_setting):
    change_app_setting('keycloak', {'ucs/self/registration/check_email_verification': True})
    with pytest.raises(samltest.SamlAccountNotVerified):
        check_login(activated_email=False)


def test_check_enabled_email_verified(change_app_setting):
    change_app_setting('keycloak', {'ucs/self/registration/check_email_verification': True})
    check_login(activated_email=True)


def check_login(activated_email=False):
    with udm_test.UCSTestUDM() as udm:
        testcase_user_name = udm.create_user(
            RegisteredThroughSelfService='TRUE',
            PasswordRecoveryEmailVerified='TRUE' if activated_email else 'FALSE',
        )[1]
        saml_session = samltest.SamlTest(testcase_user_name, 'univention')
        saml_session.login_with_new_session_at_IdP()
        saml_session.test_logged_in_status()
        saml_session.logout_at_IdP()
        saml_session.test_logout_at_IdP()
        saml_session.test_logout()
