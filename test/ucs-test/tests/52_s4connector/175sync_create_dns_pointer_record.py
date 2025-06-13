#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS PTR record
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils

import random

import univention.testing.strings as uts
import univention.testing.udm as udm_test

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        revzone = dnstests.random_reverse_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        ptr_record = uts.random_name()
        test_address = random.randrange(1, 254)
        zone_ip_parts = revzone.split('.')
        reverse_ip = f'{zone_ip_parts[2]}.{zone_ip_parts[1]}.{zone_ip_parts[0]}.in-addr.arpa'
        test_zone_dn = udm.create_object('dns/reverse_zone', subnet=revzone, nameserver=test_nameserver)
        # dnstests.check_ldap_object(test_zone_dn, 'Reverse Zone', '', '')
        test_ptr_dn = udm.create_object('dns/ptr_record', address=test_address, superordinate=test_zone_dn, ptr_record=ptr_record)
        # dnstests.check_ldap_object(test_ptr_dn, 'Pointer Record', 'pTRRecord', ptr_record)
        s4connector.wait_for_sync(30)
        dnstests.test_dns_pointer_record(reverse_ip, test_address, ptr_record)
        dnstests.check_ldap_object(test_zone_dn, 'Reverse Zone', '', '')
        dnstests.check_ldap_object(test_ptr_dn, 'Pointer Record', 'pTRRecord', ptr_record + '.')

    s4connector.wait_for_sync()
    # Removing a DNS zone triggers bind reload in postrun, better check:
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
