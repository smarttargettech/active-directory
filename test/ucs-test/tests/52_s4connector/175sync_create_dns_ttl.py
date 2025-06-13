#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS SOA ttl
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils
## bugs:
##   - 23732
## versions:
##  3.2-0: skip


import random

import univention.testing.udm as udm_test

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        test_zone_name = dnstests.random_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        test_ttl = str(random.randrange(1, 10000))
        forward_zone_dn = udm.create_object('dns/forward_zone', zone=test_zone_name, nameserver=test_nameserver, zonettl=test_ttl)
        dnstests.check_ldap_object(forward_zone_dn, 'Forward Zone TTL', 'dNSTTL', '%s' % test_ttl)
        s4connector.wait_for_sync(30)
        dnstests.test_dns_soa_ttl(test_zone_name, test_ttl)
        dnstests.check_ldap_object(forward_zone_dn, 'Forward Zone TTL', 'dNSTTL', '%s' % test_ttl)
    s4connector.wait_for_sync()
