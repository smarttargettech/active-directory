#!/usr/share/ucs-test/runner python3
## desc: Create a user via udm cli and authenticate via ldap and samba
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
##  - memberserver
## tags:
##  - basic
##  - apptest
##  - skip_admember
## packages:
##  - univention-directory-manager-tools
## exposure: dangerous
## versions:
##  3.0-0: found

import subprocess
import time

import univention.config_registry as configRegistry
import univention.testing.udm as udm_test
from univention import uldap
from univention.testing import utils


class cmd:
    def __init__(self, *args):
        self.args = args
        self.input = None

    def with_stdin(self, input):
        self.input = input
        return self

    def check(self):
        cmd = subprocess.Popen(self.args, stdin=subprocess.PIPE)

        if self.input:
            cmd.communicate(self.input.encode('UTF-8'))
        else:
            cmd.wait()

        return cmd.returncode == 0


def test_ldap_connection(ucr, user_dn, password):
    print("Testing ldap connection")
    if ucr.get('server/role').startswith('domaincontroller_'):
        access = uldap.access(binddn=user_dn, bindpw=password)
    else:
        access = uldap.access(ucr.get('ldap/master'), base=ucr.get('ldap/base'), binddn=user_dn, bindpw=password)
    for (key, value) in access.get(user_dn, required=True).items():
        print(f"{key} = {value}")


def test_samba_connection(ucr, username, password):
    # In case of a memberserver in a S4 environment, we have to
    # wait until the user has been synchronized to Samba 4. Otherwise
    # we can't get a kerberos ticket
    if ucr.get("server/role") == "memberserver":
        time.sleep(16)

    print("Try to get a kerberos ticket for the new user", username)
    kinit = cmd("kinit", "--password-file=STDIN", username).with_stdin(password)

    if not kinit.check():
        utils.fail("Failed to acquire kerberos ticket.")

    s4_installed = utils.package_installed("univention-samba4")
    if utils.package_installed("univention-samba") or s4_installed:
        host = 'localhost' if s4_installed else ucr.get('ldap/master')
        print(f"Samba Logon with this new user against {host}")

        smbclient = cmd("smbclient", "-L", host, "-U", f"{username}%{password}")

        if not smbclient.check():
            print("First Samba login failed. Wait for 30 seconds and try again ...")
            time.sleep(30)
            if not smbclient.check():
                utils.fail(f"Samba login failed for {username} with {password}")


def test(password="univention"):  # noqa: PT028
    ucr = configRegistry.ConfigRegistry()
    ucr.load()

    with udm_test.UCSTestUDM() as udm:
        (user_dn, username) = udm.create_user(wait_for=True)

        test_ldap_connection(ucr, user_dn, password)
        test_samba_connection(ucr, username, password)


if __name__ == '__main__':
    test()
