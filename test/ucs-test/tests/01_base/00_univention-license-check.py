#!/usr/share/ucs-test/runner python3
## desc: univention-license-check
## roles: [domaincontroller_master]
## tags: [apptest]
## exposure: careful
## packages:
##   - univention-config
##   - univention-directory-manager-tools

import subprocess

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils


def get_license_count(key):
    for line in subprocess.Popen(['univention-license-check'], stdout=subprocess.PIPE).communicate()[0].decode('UTF-8').split('\n'):
        if line.startswith('%s:' % key):
            return int(line.split('of')[0].split()[-1])

    raise ValueError('Could not determine license count for %s' % key)


if __name__ == '__main__':
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()

    license_mapping = {
        '1': {
            'Accounts': [{
                'users/user': {
                    'username': uts.random_username(),
                    'lastname': uts.random_name(),
                    'password': uts.random_string(),
                },
            }],
            'Clients': [{
                module: {
                        'name': uts.random_name(),
                        },
            } for module in ('computers/windows', 'computers/windows_domaincontroller', 'computers/macos')],
        },
        '2': {
            'Users': [{
                'users/user': {
                    'username': uts.random_username(),
                    'lastname': uts.random_name(),
                    'password': uts.random_string(),
                },
            }],
            'Servers': [{
                module:
                {
                        'name': uts.random_name(),
                        },
            } for module in ('computers/domaincontroller_master', 'computers/domaincontroller_backup', 'computers/domaincontroller_slave', 'computers/memberserver')],
            'Managed Clients': [{
                module: {
                    'name': uts.random_name(),
                },
            } for module in ('computers/ubuntu', 'computers/linux', 'computers/windows', 'computers/macos')],
        },
    }

    license_version = utils.get_ldap_connection().search(
        base='cn=admin,cn=license,cn=univention,%s' % ucr['ldap/base'],
        attr=['univentionLicenseVersion'])[0][1].get('univentionLicenseVersion', [b'1'])[0].decode('ASCII')
    with udm_test.UCSTestUDM() as udm:
        for asset, counting_object_types in license_mapping[license_version].items():
            license_count = get_license_count(asset)
            for object_type in counting_object_types:
                for module, attributes in object_type.items():
                    udm.create_object(module, **attributes)
                    new_license_count = get_license_count(asset)
                    if new_license_count != license_count + 1:
                        utils.fail(f'License count for {asset!r} did not raise from {license_count} to {license_count + 1} after creating a object of type {module}')

                    license_count = new_license_count
