#!/usr/share/ucs-test/runner python3
## desc: Check if ip_change also changes the ucs-sso entry
## roles-not: [basesystem]
## exposure: dangerous
## apps: [keycloak]

import sys

import atexit
from ldap.filter import filter_format

import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.config_registry import ConfigRegistry
from univention.testing import utils
from univention.testing.umc import Client


if __name__ == '__main__':
    ucr = ConfigRegistry()
    ucr.load()

    # Since the S4 connector uses a object based synchronization,
    # it is a problem to change the same object in short intervals,
    # see https://forge.univention.org/bugzilla/show_bug.cgi?id=35336
    if utils.s4connector_present():
        if ucr.get('server/role') == 'domaincontroller_master':
            atexit.register(utils.start_s4connector)
            utils.stop_s4connector()
        else:
            sys.exit(134)

    with udm_test.UCSTestUDM() as udm:
        role = ucr.get('server/role')
        sso_prefix = ucr.get('keycloak/server/sso/fqdn', 'ucs-sso-ng').split('.', 1)[0]

        # Don't create a new Master object
        if role == 'domaincontroller_master':
            role = 'domaincontroller_backup'
        computerName = uts.random_string()
        computer = udm.create_object(
            'computers/%s' % role, name=computerName,
            password='univention',
            network='cn=default,cn=networks,%s' % ucr.get('ldap/base'),
            univentionService='univention-saml',
            check_for_drs_replication=False,
        )

        lo = utils.get_ldap_connection()
        computer_object = lo.get(computer)
        print(computer_object)
        ip = computer_object['aRecord']
        utils.verify_ldap_object(computer, {'aRecord': ip})

        for ucs_sso_dn, ucs_sso_object in lo.search(filter_format('relativeDomainName=%s', [sso_prefix]), unique=True, required=True):
            ips = ucs_sso_object.get('aRecord')
            break
        else:
            raise ValueError(f'no {sso_prefix} host found.')

        lo.modify(ucs_sso_dn, [('aRecord', ips, ips + ip)])
        try:
            new_ip = '1.2.3.10'

            iface = ucr.get('interfaces/primary', 'eth0')
            client = Client(ucr.get('ldap/master'), '%s$' % computerName, 'univention')
            client.umc_command('ip/change', {'ip': new_ip, 'oldip': ip[0].decode('UTF-8'), 'netmask': ucr.get('interfaces/%s/netmask' % iface), 'role': role})

            utils.wait_for_replication()
            utils.verify_ldap_object(computer, {'aRecord': [new_ip]}, strict=True)
            utils.verify_ldap_object(ucs_sso_dn, {'aRecord': [*ips, new_ip]}, strict=True)
        finally:
            lo.modify(ucs_sso_dn, [('aRecord', lo.get(ucs_sso_dn).get('aRecord'), ips)])
