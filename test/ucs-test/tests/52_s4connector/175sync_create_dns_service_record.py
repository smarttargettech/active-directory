#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of DNS SRV record
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
        test_srv_fields = dnstests.random_srv_fields()
        location = dnstests.location()
        s4connector.stop()
        test_zone_dn = udm.create_object('dns/forward_zone', zone=test_zone_name, nameserver=test_nameserver)
        srv_record_dn = udm.create_object('dns/srv_record', superordinate=test_zone_dn, name=test_srv_fields, location=location)
        dnstests.check_ldap_object(srv_record_dn, 'Service Record', 'sRVRecord', location)
        s4connector.start()
        s4connector.wait_for_sync(30)
        temp = test_srv_fields.split(' ')
        test_string = f'_{temp[0]}._{temp[1]}.{temp[2]}.{test_zone_name}'
        dnstests.test_dns_service_record(test_string, location)
        dnstests.check_ldap_object(srv_record_dn, 'Modified Service Record', 'sRVRecord', location + '.')

    s4connector.wait_for_sync()
    # Removing a DNS zone triggers bind reload in postrun, better check:
    dnstests.fail_if_cant_resolve_own_hostname()  # wait up to 17 seconds
