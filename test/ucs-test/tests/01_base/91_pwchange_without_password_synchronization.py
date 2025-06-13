#!/usr/share/ucs-test/runner python3
## desc: Test pwchange in an environment were the new password is not synced to the kdc and password hash is {K5KEY}
## tags: [basic, skip_admember]
## roles: [domaincontroller_backup]
## exposure: dangerous
## packages: [univention-management-console-server]
## bugs: [52188]

import time

import pytest

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention import uldap
from univention.config_registry import handler_set
from univention.management.console.pam import AuthenticationFailed, PamAuth, PasswordChangeFailed, PasswordExpired
from univention.testing import utils


def create_user(uts, udm, con):
    username = uts.random_username()
    password = 'univention'
    userdn = udm.create_user(username=username, pwdChangeNextLogin=1, password=password)[0]
    # this is important, use {K5KEY} in userPassword to force
    # new ticket after pwchange in PAM krb5 module
    old_password = con.get(userdn, attr=['userPassword']).get('userPassword')[0]
    con.modify(userdn, [('userPassword', old_password, b'{K5KEY}')])
    utils.wait_for_connector_replication()
    return username, password


def test_ok(uts, udm, con):
    utils.restart_listener()
    # create user
    username, password = create_user(uts, udm, con)
    # now stop replication, do not sync new password, pwchange should work anyway
    utils.stop_listener()
    # change password
    p = PamAuth()
    for _ in range(10):
        print('trying to authenticate, may fail due to synchronization')
        try:
            with pytest.raises(PasswordExpired):
                p.authenticate(username, password)
        except AuthenticationFailed:
            print('failed, try again')
            time.sleep(3)
        else:
            print('ok we are done')
            break
    p.change_password(username, password, '123Univention.99')


def test_reproducer(uts, udm, con):
    utils.restart_listener()
    # create user
    username, password = create_user(uts, udm, con)
    # now stop replication, do not sync new password and force new ticket after pwchange
    # pwchange should fail
    handler_set(['pam/krb5/ticket_after_pwchange=true'])
    utils.stop_listener()
    p = PamAuth()
    with pytest.raises(PasswordExpired):
        p.authenticate(username, password)
    # with ticket_after_pwchange=true password change should fail
    with pytest.raises(PasswordChangeFailed):
        p.change_password(username, password, '123Univention.99')


if __name__ == '__main__':
    con = uldap.getAdminConnection()
    with udm_test.UCSTestUDM() as udm, ucr_test.UCSTestConfigRegistry() as ucr:
        try:
            # only this backup is kdc
            handler_set(['kerberos/kdc=%(hostname)s.%(domainname)s' % ucr])
            handler_set(['kerberos/defaults/dns_lookup_kdc=false'])
            test_ok(uts, udm, con)
            # this particular problem can't be reproduced with samba,
            # so ignore the reproducer, just test if it works
            if not utils.package_installed('univention-samba4'):
                test_reproducer(uts, udm, con)
        finally:
            utils.restart_listener()
