#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS SOA serial
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils
## bugs:
##   - 32156

import univention.admin.modules as udm_modules
import univention.admin.uldap
import univention.testing.udm as udm_test
from univention.testing import utils

import dnstests
import s4connector


udm_modules.update()


def get_serial_number(zone_dn):
    lo = utils.get_ldap_connection(admin_uldap=True)
    position = univention.admin.uldap.position(lo.base)
    udm_modules.init(lo, position, udm_modules.get('dns/forward_zone'))
    results = udm_modules.lookup('dns/forward_zone', None, lo, base=zone_dn, scope='base')
    udm_object = results[0]
    udm_object.open()
    return udm_object['serial']


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        test_zone = dnstests.random_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        test_zone_dn = udm.create_object('dns/forward_zone', zone=test_zone, nameserver=test_nameserver)
        # dnstests.check_ldap_object(forward_zone, 'forward zone')
        s4connector.wait_for_sync(30)

        serial = get_serial_number(test_zone_dn)
        print("Forward zone serial : " + serial)
        dnstests.test_dns_serial(test_zone, serial)
        # dnstests.check_ldap_object(test_zone_dn, 'forward zone')

    s4connector.wait_for_sync()
    # Removing a DNS zone triggers bind reload in postrun, better check:
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
