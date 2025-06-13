#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS CNAME record
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils

import univention.testing.udm as udm_test

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        test_zone_name = dnstests.random_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        test_hostname = '*'
        test_ipv4address = dnstests.make_random_ip()
        test_zone_dn = udm.create_object('dns/forward_zone', zone=test_zone_name, nameserver=test_nameserver)
        dns_record_dn = udm.create_object('dns/host_record', superordinate=test_zone_dn, name=test_hostname, a=test_ipv4address)
        dnstests.check_ldap_object(dns_record_dn, 'host_record', 'aRecord', test_ipv4address)
        s4connector.wait_for_sync(30)

        test_fqdn = test_hostname + '.' + test_zone_name
        dnstests.test_dns_a_record(test_fqdn, test_ipv4address)
        dnstests.check_ldap_object(dns_record_dn, 'host_record', 'aRecord', test_ipv4address)

    s4connector.wait_for_sync()
    # Removing a DNS zone triggers bind reload in postrun, better check:
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
