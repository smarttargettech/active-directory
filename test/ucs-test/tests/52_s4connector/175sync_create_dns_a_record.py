#!/usr/share/ucs-test/runner python3
## desc: s4connector bidirectional sync of DNS A record (on zone)
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils

import sys

import univention.testing.udm as udm_test
from univention.testing.utils import wait_for_replication_and_postrun

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()
    with udm_test.UCSTestUDM() as udm:
        print("========== create DNS zone in UDM ==========")
        sys.stdout.flush()
        ip = dnstests.make_random_ip()
        random_zone = dnstests.random_zone()
        test_nameserver = dnstests.get_hostname_of_ldap_master()
        test_zone_dn = udm.create_object('dns/forward_zone', zone=random_zone, nameserver=test_nameserver, a=ip)
        dnstests.check_ldap_object(test_zone_dn, 'A Record', 'aRecord', ip)
        # Adding a DNS zone triggers bind reload in postrun
        wait_for_replication_and_postrun()
        s4connector.wait_for_sync()

        dnstests.test_dns_a_record(random_zone, ip)
        dnstests.check_ldap_object(test_zone_dn, 'A Record', 'aRecord', ip)

        print("========== modify address in Samba ==========")
        dnstests.get_kerberos_ticket_for_machine()

        # Adding a DNS zone triggers bind reload in postrun, better check:
        dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds

        ip2 = dnstests.make_random_ip()
        nsupdate_add_request = '''server %(hostname)s.%(domainname)s
zone %(zonename)s.
; debug yes
; update delete %(zonename)s. A
update add %(zonename)s. %(ttl)s IN A %(ip)s
; show
send
quit''' % {
            "hostname": dnstests.ucr["hostname"],
            "domainname": dnstests.ucr["domainname"],
            "zonename": random_zone,
            "ttl": 1200,
            "ip": ip2,
        }

        dnstests.nsupdate(nsupdate_add_request)

        s4connector.wait_for_sync()
        dnstests.test_dns_a_record(random_zone, ip2)
        dnstests.check_ldap_object(test_zone_dn, 'A Record', 'aRecord', [ip, ip2])

    sys.stdout.flush()

    # Removing a DNS zone triggers bind reload in postrun, better check:
    wait_for_replication_and_postrun()
    s4connector.wait_for_sync()
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
