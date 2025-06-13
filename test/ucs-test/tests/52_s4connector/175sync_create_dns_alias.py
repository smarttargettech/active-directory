#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS CNAME record
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
#   - bind9-dnsutils

import univention.testing.strings as uts
import univention.testing.udm as udm_test

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        test_zone_name = dnstests.random_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        random_name1 = uts.random_string()
        random_name2 = uts.random_string()
        test_zone_dn = udm.create_object('dns/forward_zone', zone=test_zone_name, nameserver=test_nameserver)
        dns_alias_dn = udm.create_object('dns/alias', superordinate=test_zone_dn, name=random_name1, cname=random_name2)
        dnstests.check_ldap_object(dns_alias_dn, 'alias', 'cNAMERecord', random_name2)
        s4connector.wait_for_sync(30)

        test_fqdn = random_name1 + '.' + test_zone_name
        dnstests.test_dns_alias(test_fqdn, random_name2)
        dnstests.check_ldap_object(dns_alias_dn, 'alias', 'cNAMERecord', random_name2)

    s4connector.wait_for_sync()
    # Removing a DNS zone triggers bind reload in postrun, better check:
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
