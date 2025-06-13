#!/usr/share/ucs-test/runner python3
## desc: |
##  Check if kpasswd spuriously reports success
##  This script tests if kpasswd spuriously reports success when trying to change the password to a too short one.
##  It performs the following steps for the test:
##  * Create user with "long password"
##  * Log in with this user using ssh
##  * Try to change password with kpasswd to "too short password" and parse its output
##  * Test "long password" and "too short password" by trying to log in using ssh
## tags: [basic,skip_admember]
## bugs: [10013]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## versions:
##  2.2-0: fixed
## packages:
##  - python3-pexpect
##  - univention-heimdal-kdc
## exposure: dangerous

import os
import random
import sys
import tempfile

import pexpect

import univention.config_registry
import univention.testing.udm as udm_test


ucr = univention.config_registry.ConfigRegistry()
ucr.load()


def create_ssh_session(username, password):
    known_hosts_file = tempfile.NamedTemporaryFile()
    os.environ["TERM"] = "xterm-mono"
    shell = pexpect.spawn('ssh', ['-o', 'UserKnownHostsFile="%s"' % known_hosts_file.name, '%s@localhost' % username], timeout=10)  # logfile=sys.stdout)
    status = shell.expect([pexpect.TIMEOUT, '[Pp]assword: ', 'Are you sure you want to continue connecting'])
    del known_hosts_file
    if status == 2:  # accept public key
        shell.sendline('yes')
        status = shell.expect([pexpect.TIMEOUT, '[Pp]assword: '])
    if status == 0:  # timeout
        raise Exception('ssh behaved unexpectedly! Output:\n\t%r' % (shell.before,))
    assert status == 1, "password prompt"
    shell.sendline(password)
    status = shell.expect([pexpect.TIMEOUT, 'Permission denied', r':~\$'])
    if status == 0:  # timeout
        raise Exception('No shell prompt found! Output:\n\t%r' % (shell.before,))
    if status == 1:  # permission denied
        raise Exception('ssh error: Permission denied.')
    assert status == 2, 'shell prompt'
    return shell


if __name__ == "__main__":
    with udm_test.UCSTestUDM() as udm:
        password = '%010x' % (random.getrandbits(40),)
        (user_dn, username) = udm.create_user(
            password=password,
            primaryGroup='cn=%s,cn=groups,%s' % (ucr.get('groups/default/domainadmins', 'Domain Admins'), ucr['ldap/base']),
            wait_for=True,
        )

        try:
            shell = create_ssh_session(username, password)
        except Exception as e:
            print(e)  # print error
            sys.exit(120)

        newpassword = '%02x' % (random.getrandbits(8),)  # a short password to trigger the bug
        shell.sendline('kpasswd')
        status = shell.expect([pexpect.TIMEOUT, '[Pp]assword:'])
        if status == 0:  # timeout
            print('kpasswd behaved unexpectedly! Output:\n\t%r' % (shell.before,))
            sys.exit(120)
        shell.sendline(password)
        status = shell.expect([pexpect.TIMEOUT, 'New password:'])
        shell.sendline(newpassword)
        status = shell.expect([pexpect.TIMEOUT, 'New password:'])
        shell.sendline(newpassword)
        status = shell.expect(['(?i)[Ss]uccess', '(?i)[Ee]rror', pexpect.TIMEOUT])
        kpasswd_reported_success = status == 0

        try:
            create_ssh_session(username, password)
            accepted_old_pwd = True
        except Exception:
            accepted_old_pwd = False
        try:
            create_ssh_session(username, newpassword)
            accepted_new_pwd = True
        except Exception:
            accepted_new_pwd = False
        if accepted_old_pwd == accepted_new_pwd:
            print('ERROR: Both passwords were', end=' ')
            if accepted_old_pwd and accepted_new_pwd:
                print('accepted')
            else:
                print('rejected')
            sys.exit(120)  # Transient error
        password_changed = accepted_new_pwd

        if kpasswd_reported_success:
            print('TEST FAILED: "kpasswd" reported acceptance of too short password', end=' ')
        else:
            print('TEST SUCCEEDED: "kpasswd" reported refusal of too short password', end=' ')
        if kpasswd_reported_success == password_changed:
            print('and', end=' ')
        else:
            print('but', end=' ')
        if password_changed:
            print('the password was changed')
        else:
            print('the password was not changed')
        if password_changed:
            print('\tThe short password "%s" was accepted - this should not happen.' % (newpassword,))
            sys.exit(120)  # Transient error

        if kpasswd_reported_success:
            sys.exit(1)
        else:
            sys.exit(0)

# vim: set ft=python :
