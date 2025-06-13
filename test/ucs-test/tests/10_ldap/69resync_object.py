#!/usr/share/ucs-test/runner python3
## desc: Check the resync_objects.py script supplied with the listener
## tags:
##  - replication
## roles:
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages-not:
##  - univention-samba4
## exposure: dangerous

import subprocess
import time

import ldap

import univention.testing.strings as uts
from univention.testing import utils
from univention.testing.udm import UCSTestUDM
from univention.uldap import getRootDnConnection


def test_resync_missing_object():
    print('Testing resync of missing object')
    with UCSTestUDM() as udm:
        user_dn, user_name = udm.create_user()
        utils.wait_for_listener_replication()
        # just wait at this point, we need to make sure to openldap samba ping
        # pong has stopped, so that we can remove the object in the local
        # ldap without getting the object back from samba
        time.sleep(30)
        user_filter = ldap.filter.filter_format('uid=%s', (user_name, ))
        local_lo = getRootDnConnection()
        local_lo.delete(user_dn)
        if local_lo.searchDn(user_filter):
            utils.fail("Could not delete user from local ldap")
        fail_update = subprocess.check_output([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--update',
            '--filter',
            user_filter,
        ]).decode('UTF-8')
        if fail_update != f'resync from Primary: {user_dn}\n  ==> object does not exist, can not update\n':
            utils.fail(f'Updating a nonexisting object should not work: {fail_update}')
        simulation = subprocess.check_output([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--simulate',
            '--filter',
            user_filter,
        ]).decode('UTF-8')
        if simulation != f'resync from Primary: {user_dn}\n  ==> adding object\n':
            utils.fail(f'Unexpected output from simulation: {simulation}')
        if local_lo.searchDn(user_filter):
            utils.fail('Simulation changed local ldap')
        print('OK: simulation works')
        subprocess.check_call([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--filter',
            user_filter,
        ])
        if not local_lo.searchDn(user_filter):
            utils.fail('Object not resynced')
        print('OK: could resync missing object')


def test_resync_updating_object():
    print('Testing resync updating object')
    with UCSTestUDM() as udm:
        user_dn, user_name = udm.create_user()
        user_filter = ldap.filter.filter_format('uid=%s', (user_name, ))
        local_lo = getRootDnConnection()
        user_sn = local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0]
        user_sn_new = uts.random_string().encode('UTF-8')
        local_lo.modify(user_dn, [('sn', user_sn, user_sn_new)])
        if local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0] != user_sn_new:
            utils.fail('Local object modification failed')
        fail_create = subprocess.check_output([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--filter',
            user_filter,
        ]).decode('UTF-8')
        if fail_create != f'resync from Primary: {user_dn}\n  ==> object does exist, can not create\n':
            utils.fail(f'Creating an existing object should not work: {fail_create}')
        simulation = subprocess.check_output([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--simulate',
            '--update',
            '--filter',
            user_filter,
        ]).decode('UTF-8')
        if simulation != f'resync from Primary: {user_dn}\n  ==> modifying object\n':
            utils.fail(f'Unexpected output from simulation: {simulation}')
        if local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0] != user_sn_new:
            utils.fail('Simulation changed local ldap')
        print('OK: simulation works')
        subprocess.check_call([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--update',
            '--filter',
            user_filter,
        ])
        if local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0] != user_sn:
            utils.fail('Object not resynced')
        print('OK: could resync updating object')


def test_resync_recreate_object():
    print('Testing resync recreate object')
    with UCSTestUDM() as udm:
        user_dn, user_name = udm.create_user()
        user_filter = ldap.filter.filter_format('uid=%s', (user_name, ))
        local_lo = getRootDnConnection()
        user_sn = local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0]
        user_sn_new = uts.random_string().encode('UTF-8')
        local_lo.modify(user_dn, [('sn', user_sn, user_sn_new)])
        if local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0] != user_sn_new:
            utils.fail('Local object modification failed')
        simulation = subprocess.check_output([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--simulate',
            '--remove',
            '--filter',
            user_filter,
        ]).decode('UTF-8')
        if simulation != f'remove from local: {user_dn}\nresync from Primary: {user_dn}\n  ==> adding object\n':
            utils.fail(f'Unexpected output from simulation: {simulation}')
        if local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0] != user_sn_new:
            utils.fail('Simulation changed local ldap')
        print('OK: simulation works')
        subprocess.check_call([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--remove',
            '--filter',
            user_filter,
        ])
        if local_lo.search(user_filter, attr=('sn',))[0][1]['sn'][0] != user_sn:
            utils.fail('Object not resynced')
        print('OK: could resync recreate object')


def test_resync_remove_object():
    print('Testing resync remove object')
    local_lo = getRootDnConnection()
    container_name = uts.random_name()
    container_dn = f'cn={container_name},{local_lo.base}'
    container_filter = ldap.filter.filter_format('cn=%s', (container_name, ))
    fail_remove = subprocess.check_output([
        '/usr/share/univention-directory-listener/resync-objects.py',
        '--remove',
        '--filter',
        container_filter,
    ]).decode('UTF-8')
    if fail_remove != 'object does not exist local\nobject does not exist on Primary\n':
        utils.fail(f'Script should not have done anything: {fail_remove}')
    local_lo.add(container_dn, [('objectClass', b'organizationalRole'), ('cn', container_name.encode('UTF-8'))])
    try:
        if not local_lo.searchDn(container_filter):
            utils.fail("Could not add container to local ldap")
        simulation = subprocess.check_output([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--simulate',
            '--remove',
            '--filter',
            container_filter,
        ]).decode('UTF-8')
        if simulation != f'remove from local: {container_dn}\nobject does not exist on Primary\n':
            utils.fail(f'Unexpected output from simulation: {simulation}')
        if not local_lo.searchDn(container_filter):
            utils.fail('Simulation changed local ldap')
        print('OK: simulation works')
        subprocess.check_call([
            '/usr/share/univention-directory-listener/resync-objects.py',
            '--remove',
            '--filter',
            container_filter,
        ])
        if local_lo.searchDn(container_filter):
            utils.fail('Object not resynced')
        print('OK: could resync remove object')
    finally:
        try:
            local_lo.delete(container_dn)
        except ldap.NO_SUCH_OBJECT:
            pass


def main():
    test_resync_missing_object()
    test_resync_updating_object()
    test_resync_recreate_object()
    test_resync_remove_object()


if __name__ == '__main__':
    main()
