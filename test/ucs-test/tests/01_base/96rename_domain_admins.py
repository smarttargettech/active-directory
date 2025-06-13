#!/usr/share/ucs-test/runner python3
## desc: Rename Domain Admins
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
from univention.testing.utils import package_installed


def search_templates(old_group_name, new_group_name, server_role):
    templates = glob.glob('/etc/univention/templates/info/*.info')
    file_content = []
    file_pattern = re.compile('^(Multifile: |File: )')
    # find all template files by iterating over all referenced templates in the ucr *.info files
    for template in templates:
        with open(template) as content_file:
            # find all lines that start with File or Multifile and strip it to get the paths of the template files
            file_content += ['/' + file_pattern.sub('', line).strip() for line in content_file.readlines() if file_pattern.match(line)]

    # A list of templates which are referencing the defaultdomainadmins group. The new name must be found in them
    should_contain_admin = [
        '/etc/security/access-rlogin.conf', '/etc/security/access-ftp.conf',
        '/etc/security/access-screen.conf', '/etc/security/access-gdm.conf',
        '/etc/security/access-login.conf', '/etc/security/access-other.conf',
        '/etc/security/access-kdm.conf', '/etc/security/access-sshd.conf',
    ]
    ignore = ['/etc/security/access-ppp.conf', '/etc/sudoers.d/univention']
    if server_role == 'memberserver':
        should_contain_admin.append('/etc/ldap/slapd.conf')
        should_contain_admin.remove('/etc/security/access-sshd.conf')

    # Check if the name was correctly updated in the templates
    file_content = list(dict.fromkeys(file_content))
    for filename in file_content:
        if not os.path.isfile(filename) or filename in ignore:
            continue

        print(f'Checking template {filename}')
        with open(filename, 'rb') as content_file:
            content = content_file.read().decode('UTF-8', 'replace')

        # contains a comment about the group
        if filename in should_contain_admin and new_group_name not in content:
            utils.fail(f'FAIL: New group name {new_group_name} not in {filename}')

        # Contain comments or something about the group
        if old_group_name in content:
            lines_containing = [line for line in content.splitlines() if old_group_name in line]
            # Workaround for Bug #51975: Please remove if fixed
            if filename == '/etc/ldap/slapd.conf' and package_installed('univention-radius') and len(lines_containing) == 1:
                print('/etc/ldap/slapd.conf contains the old_group_name due to http://forge.univention.org/bugzilla/show_bug.cgi?id=51975')
                print('Ignore until fixed')
                continue

            print('\n'.join(lines_containing))
            utils.fail(f'FAIL: Old group name {old_group_name} still in file {filename}')


def wait_for_ucr(iterations, group_name, ucr_test):
    success = False
    for i in range(iterations):
        ucr_test.load()
        ucr_group = ucr_test.get('groups/default/domainadmins', 'Domain Admins')
        if group_name != ucr_group:
            if i == iterations - 1:
                break
            time.sleep(15)
        else:
            print(f'UCR variable groups/default/domainadmins is set correctly to {ucr_group}')
            success = True
            break
    return success, ucr_group


def test_rename_domain_users():
    with UCSTestConfigRegistry() as ucr_test:
        ucr_test.load()

        server_role = ucr_test.get('server/role')
        ldap_base = ucr_test.get('ldap/base')
        old_group_name = ucr_test.get('groups/default/domainadmins', 'Domain Admins')
        old_group_dn = f"cn={escape_dn_chars(old_group_name)},cn=groups,{ldap_base}"

        new_group_name = uts.random_name()
        new_group_dn = f"cn={escape_dn_chars(new_group_name)},cn=groups,{ldap_base}"
        try:
            print('\n##################################################################')
            print(f'Renaming default domainadmins group {old_group_name} to {new_group_name}')
            print('##################################################################\n')
            subprocess.call(['udm-test', 'groups/group', 'modify', '--dn=%s' % (old_group_dn), '--set', 'name=%s' % (new_group_name)])
            utils.wait_for_replication_and_postrun()

            # Check UCR Variable
            print('\n##################################################################')
            print(f'Checking if UCR Variable groups/default/domainadmins is set to {new_group_name}')
            print('##################################################################\n')

            success, ucr_group = wait_for_ucr(10, new_group_name, ucr_test)
            if not success:
                utils.fail(f'UCR variable groups/default/domainusers was set to {old_group_name} instead of {new_group_name}')

            # in ucs5 the time between setting the ucr var and the change being committed to the configuration files is longer than expected:
            time.sleep(10)

            # Search templates
            print('\n##################################################################')
            print('Search templates for old and new name of default domainadmins group')
            print('##################################################################\n')
            search_templates(old_group_name, new_group_name, server_role)
        finally:
            try:
                wait_for_drs_replication(filter_format('(sAMAccountName=%s)', (new_group_name,)))
            except Exception:
                # clean up even if the wait_for method fails and wait a bit if it terminated at the beginning
                time.sleep(10)

            if not package_installed('univention-samba4'):
                time.sleep(20)

            print('\n##################################################################')
            print('Cleanup')
            print('##################################################################\n')
            subprocess.call(['udm-test', 'groups/group', 'modify', '--dn=%s' % (new_group_dn), '--set', 'name=%s' % (old_group_name)])

            # wait until renaming and UCR Variable is set back again
            utils.wait_for_replication_and_postrun()
            success, ucr_group = wait_for_ucr(10, old_group_name, ucr_test)
            if not success:
                univention.config_registry.handler_set(['groups/default/domainadmins=Domain Admins'])
                utils.fail(f'UCR variable groups/default/domainadmins was set to {ucr_group} instead of {new_group_name}')


if __name__ == '__main__':
    test_rename_domain_users()
