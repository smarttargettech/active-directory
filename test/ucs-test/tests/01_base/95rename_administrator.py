#!/usr/share/ucs-test/runner python3
## desc: Rename Administrator
## tags:
##  - basic
##  - rename_default_account
##  - skip_admember
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
##  - memberserver
## exposure: dangerous


import glob
import os
import re
import subprocess
import time

from ldap.dn import escape_dn_chars
from ldap.filter import filter_format

import univention.config_registry
import univention.testing.strings as uts
from univention.testing import utils
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.udm import UCSTestUDM
from univention.testing.utils import package_installed


def search_templates(old_admin_name, new_admin_name, server_role):
    templates = glob.glob('/etc/univention/templates/info/*.info')
    file_content = []
    file_pattern = re.compile('^(Multifile: |File: )')

    # find all template files by iterating over all referenced templates in the ucr *.info files
    for template in templates:
        with open(template) as content_file:
            # find all lines that start with File or Multifile and strip it to get the paths of the template files
            file_content += ['/' + file_pattern.sub('', line).strip() for line in content_file.readlines() if file_pattern.match(line)]

    # A list of templates which are referencing the Administrator. The new name must be found in them
    should_contain_admin = [
        '/etc/ldap/slapd.conf',
    ]
    ignore = [
        '/etc/freeradius/3.0/mods-available/ldap',
        '/etc/bind/named.conf.samba4', '/var/www/univention/meta.json',
        '/etc/issue', '/etc/welcome.msg', '/etc/samba/base.conf', '/etc/cups/cups-files.conf',
        '/var/lib/univention-appcenter/apps/keycloak/conf/UCS/login/messages/messages_de.properties',
    ]
    if server_role != 'domaincontroller_master':
        should_contain_admin.remove('/etc/ldap/slapd.conf')

    # Check if the name was correctly updated in the templates
    file_content = list(dict.fromkeys(file_content))

    # Look for alle occurences of "Administrator", excluding "Administrators", which is a group name
    for file in file_content:
        if not os.path.isfile(file) or file in ignore:
            continue

        print(f'Checking template {file}')
        with open(file, 'rb') as content_file:
            content = content_file.read().decode('UTF-8', 'replace')

        if file in should_contain_admin and new_admin_name not in content:
            utils.fail(f'FAIL: New admin name {new_admin_name} not in {file}')

        if old_admin_name in content:
            lines_containing = [line for line in content.splitlines() if old_admin_name in line and 'Administrators' not in line]
            if lines_containing:
                print('\n'.join(lines_containing))
                utils.fail(f'FAIL: Old group name {old_admin_name} still in file {file}')


def wait_for_ucr(iterations, admin_name, ucr_test):
    success = False
    for i in range(iterations):
        ucr_test.load()
        ucr_name = ucr_test.get('users/default/administrator', 'Administrator')
        if admin_name != ucr_name:
            if i == iterations - 1:
                break
            time.sleep(15)
        else:
            print(f'UCR variable users/default/administrator is set correctly to {ucr_name}')
            success = True
            break
    return success, ucr_name


def test_rename_domain_users():
    with UCSTestConfigRegistry() as ucr_test, UCSTestUDM() as udm:
        ucr_test.load()

        server_role = ucr_test.get('server/role')
        ldap_base = ucr_test.get('ldap/base')
        old_admin_name = ucr_test.get('users/default/administrator', 'Administrator')
        old_admin_dn = f"uid={escape_dn_chars(old_admin_name)},cn=users,{ldap_base}"
        if os.path.exists('/etc/ldap.secret'):
            credentials = ['--binddn', f'cn=admin,{ldap_base}', '--bindpwdfile', '/etc/ldap.secret']
        else:
            second_admin = udm.create_user(append={'groups': [f'cn=Domain Admins,cn=groups,{ldap_base}']})[0]
            credentials = ['--binddn', second_admin, '--bindpwd', 'univention']

        new_admin_name = uts.random_name()
        new_admin_dn = f"uid={escape_dn_chars(new_admin_name)},cn=users,{ldap_base}"
        try:
            print('\n##################################################################')
            print(f'Renaming default administrator {old_admin_name} to {new_admin_name}')
            print('##################################################################\n')
            print(old_admin_dn)
            print(new_admin_name)
            cmd = ['udm-test', 'users/user', 'modify', '--dn=%s' % (old_admin_dn), '--set', 'username=%s' % (new_admin_name)]
            cmd.extend(credentials)
            subprocess.call(cmd)
            utils.wait_for_replication_and_postrun()

            # Check UCR Variable
            print('\n##################################################################')
            print(f'Checking if UCR Variable users/default/administrator is set to {new_admin_name}')
            print('##################################################################\n')

            success, ucr_name = wait_for_ucr(3, new_admin_name, ucr_test)
            if not success:
                utils.fail(f'UCR variable users/default/administrator was set to {old_admin_name} instead of {new_admin_name}')

            # Search templates
            print('\n##################################################################')
            print('Search templates for old and new name of default domainadmins group')
            print('##################################################################\n')
            search_templates(old_admin_name, new_admin_name, server_role)
        finally:
            try:
                wait_for_drs_replication(filter_format('(sAMAccountName=%s)', (new_admin_name,)))
            except Exception:
                # clean up even if the wait_for method fails and wait a bit if it terminated at the beginning
                time.sleep(10)

            if not package_installed('univention-samba4'):
                time.sleep(20)
            print('\n##################################################################')
            print('Cleanup')
            print('##################################################################\n')
            subprocess.call(['udm-test', 'users/user', 'modify', '--dn=%s' % new_admin_dn, '--set', 'username=%s' % old_admin_name, '--binddn=%s' % new_admin_dn, '--bindpwd=univention', *credentials])

            # wait until renaming and UCR Variable is set back again
            utils.wait_for_replication_and_postrun()
            success, ucr_name = wait_for_ucr(10, old_admin_name, ucr_test)
            if not success:
                univention.config_registry.handler_set(['users/default/administrator=Administrator'])
                utils.fail(f'UCR variable users/default/administrator was set to {ucr_name} instead of {old_admin_name}')


if __name__ == '__main__':
    test_rename_domain_users()
