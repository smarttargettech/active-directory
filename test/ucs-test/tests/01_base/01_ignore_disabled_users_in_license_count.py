#!/usr/share/ucs-test/runner python3
## desc: Disabled users should be ignored in the license counter
## roles: [domaincontroller_master]
## exposure: careful
## bugs: [22457]
## packages:
##   - univention-config
##   - univention-directory-manager-tools

import subprocess

import univention.testing.udm as udm_test
from univention.testing import utils


def get_current_license_user_count():
    for line in subprocess.Popen(['univention-license-check'], stdout=subprocess.PIPE).communicate()[0].decode('UTF-8').split('\n'):
        if line.startswith(('Accounts:', 'Users:')):
            return int(line.split('of')[0].split()[-1])

    raise ValueError('Could not determine license user count')


if __name__ == '__main__':
    license_user_count = get_current_license_user_count()

    with udm_test.UCSTestUDM() as udm:
        udm.create_user(disabled='1')
        new_license_user_count = get_current_license_user_count()

        if new_license_user_count != license_user_count:
            utils.fail(f'After creating a fully disabled user, the license user counter raised from {license_user_count} to {new_license_user_count}')

        for disabled in ('0', '1', '0'):
            udm.create_user(disabled=disabled)
            new_license_user_count = get_current_license_user_count()
            if disabled == '0':
                if new_license_user_count != license_user_count + 1:
                    utils.fail(f'After creating a user with {disabled!r} disabled, the license user counter did not raise from {license_user_count} to {license_user_count + 1}')
                license_user_count = new_license_user_count
