#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS TXT record (on zone)
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils
## versions:
##  3.2-0: skip
##  4.2-0: fixed

import univention.testing.strings as uts
import univention.testing.udm as udm_test

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        test_zone_name = dnstests.random_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        txt = uts.random_string()
        test_zone_dn = udm.create_object('dns/forward_zone', zone=test_zone_name, txt=txt, nameserver=test_nameserver)
        dnstests.check_ldap_object(test_zone_dn, 'txt record', 'tXTRecord', txt)
        s4connector.wait_for_sync(30)
        dnstests.test_dns_txt(test_zone_name, txt)
        dnstests.check_ldap_object(test_zone_dn, 'txt record', 'tXTRecord', txt)

    s4connector.wait_for_sync()
    # Removing a DNS zone triggers bind reload in postrun, better check:
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
