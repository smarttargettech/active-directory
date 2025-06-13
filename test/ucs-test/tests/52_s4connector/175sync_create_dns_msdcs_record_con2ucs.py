#!/usr/share/ucs-test/runner python3
## desc: s4connector con2ucs sync of _msdcs DNS SRV record
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils

import sys

import univention.testing.strings as uts
from univention.testing import utils

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()

    print("========== Create DNS SRV record via nsupdate ==========")
    dnstests.get_kerberos_ticket_for_machine()

    domainname = dnstests.ucr["domainname"]
    hostname = dnstests.ucr["hostname"]
    fqdn = f'{hostname}.{domainname}'
    location = "0 100 389 %s." % fqdn
    forward_zone_dn = "zoneName=%s,cn=dns,%s" % (domainname, dnstests.ucr["ldap/base"])

    test_relativeDomainName = "_%s._msdcs" % uts.random_name()
    test_srv_record_dn = "relativeDomainName=%s,%s" % (test_relativeDomainName, forward_zone_dn)
    test_fqdn = "%s.%s" % (test_relativeDomainName, domainname)
    s4_zonename = "_msdcs.%s" % (domainname,)

    nsupdate_add_request = '''server %(hostname)s.%(domainname)s
zone %(zonename)s.
; debug yes
; update delete %(zonename)s. A
update add %(test_fqdn)s. %(ttl)s IN SRV %(location)s
; show
send
quit''' % {
        "hostname": hostname,
        "domainname": domainname,
        "zonename": s4_zonename,
        "test_fqdn": test_fqdn,
        "ttl": 1200,
        "location": location,
    }

    dnstests.nsupdate(nsupdate_add_request)

    dnstests.test_dns_service_record(test_fqdn, location)

    s4connector.wait_for_sync(30)
    dnstests.check_ldap_object(test_srv_record_dn, 'Service Record', 'sRVRecord', location)

    sys.stdout.flush()

    # TODO: remove again
    nsupdate_del_request = '''server %(hostname)s.%(domainname)s
zone %(zonename)s.
; debug yes
update delete %(test_fqdn)s. SRV
; show
send
quit''' % {
        "hostname": hostname,
        "domainname": domainname,
        "zonename": s4_zonename,
        "test_fqdn": test_fqdn,
    }

    dnstests.nsupdate(nsupdate_del_request)
    dnstests.test_dns_service_record(test_fqdn, ".*", should_exist=False)

    # TODO: DDNS/con2ucs removal sync doesn't work (Bug #39161)
    # Workaround: Remove via UDM instead:
    dnstests.udm_remove_dns_record_object('dns/srv_record', test_srv_record_dn)

    s4connector.wait_for_sync()
    utils.verify_ldap_object(test_srv_record_dn, should_exist=False)
