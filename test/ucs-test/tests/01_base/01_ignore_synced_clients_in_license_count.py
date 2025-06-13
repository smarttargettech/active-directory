#!/usr/share/ucs-test/runner python3
## desc: Clients flagged as "synced" should be ignored in the license count
## roles: [domaincontroller_master]
## exposure: careful
## bugs: [35647]
## tags: [udm]
## packages:
##   - univention-config
##   - univention-directory-manager-tools

import subprocess

import univention.config_registry
import univention.testing.strings as uts
from univention.testing import utils
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.udm import UCSTestUDM


def get_current_v2license_client_count():
    for line in subprocess.Popen(['univention-license-check'], stdout=subprocess.PIPE).communicate()[0].decode('UTF-8').split('\n'):
        if line.startswith('Managed Clients:'):
            return int(line.split('of')[0].split()[-1])

    raise ValueError('Could not determine license client count')


if __name__ == '__main__':
    lo = utils.get_ldap_connection()

    with UCSTestConfigRegistry() as ucr_test:
        with UCSTestUDM() as udm:
            univention.config_registry.handler_unset(['ad/member'])
            udm.stop_cli_server()
            license_client_count_initial = get_current_v2license_client_count()

            univention.config_registry.handler_set(['ad/member=true'])
            udm.stop_cli_server()
            license_client_count_admember = get_current_v2license_client_count()

            attributes = {
                'name': uts.random_name(),
            }
            client_dn = udm.create_object('computers/windows', **attributes)
            utils.wait_for_replication()
            udm.stop_cli_server()
            license_client_count_current = get_current_v2license_client_count()
            if license_client_count_current != license_client_count_admember + 1:
                utils.fail(f'After creating a normal client in ad/member mode, the license client counter did not increase by one (admember: {license_client_count_admember}, current: {license_client_count_current})')

            lo.modify(client_dn, (('univentionObjectFlag', b'', b'synced'),))
            utils.wait_for_replication()
            udm.stop_cli_server()
            license_client_count_current = get_current_v2license_client_count()
            if license_client_count_current != license_client_count_admember:
                utils.fail(f'After flagging the test client as synced in ad/member mode, the client is still counted in the license (admember: {license_client_count_admember}, current: {license_client_count_current})')

            univention.config_registry.handler_unset(['ad/member'])
            udm.stop_cli_server()

            license_client_count_current = get_current_v2license_client_count()
            if license_client_count_current != license_client_count_initial + 1:
                utils.fail(f"After disabling ad/member mode, the 'synced' client is still ignored (initial: {license_client_count_initial}, current: {license_client_count_current})")
