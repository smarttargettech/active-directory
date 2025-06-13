#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Check that the umc server does not stop if the idp metadata is not available.
## tags: [saml]
## bugs: [39355]
## join: true
## exposure: dangerous

import os
import subprocess
import time

import pytest

import samltest


def restart_umc():
    subprocess.check_call(["deb-systemd-invoke", "restart", "univention-management-console-server"])
    time.sleep(3)  # Wait for the umc to be ready to answer requests.


class move_idp_metadata:

    metadata_dir = "/usr/share/univention-management-console/saml/idp/"

    def __enter__(self):
        for metadata_file in os.listdir(self.metadata_dir):
            metadata_file_fullpath = self.metadata_dir + metadata_file
            os.rename(metadata_file_fullpath, metadata_file_fullpath + '.backup')
        restart_umc()

    def __exit__(self, exc_type, exc_value, traceback):
        for metadata_file in os.listdir(self.metadata_dir):
            metadata_file_fullpath = self.metadata_dir + metadata_file
            os.rename(metadata_file_fullpath, metadata_file_fullpath.replace('.backup', ''))
        restart_umc()


@pytest.fixture(autouse=True)
def cleanup():
    yield
    restart_umc()


def test_broken_idp_metadata(saml_session):
    with move_idp_metadata():
        with pytest.raises(samltest.SamlError) as exc:
            saml_session.login_with_new_session_at_IdP()
        expected_error = "There is a configuration error in the service provider: No identity provider are set up for use."
        assert expected_error in str(exc.value)

    saml_session.login_with_new_session_at_IdP()
    saml_session.test_logged_in_status()
    saml_session.logout_at_IdP()
    saml_session.test_logout_at_IdP()
    saml_session.test_logout()
