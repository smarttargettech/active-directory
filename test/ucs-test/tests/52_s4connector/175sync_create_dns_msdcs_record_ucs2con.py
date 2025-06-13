#!/usr/share/ucs-test/runner python3
## desc: s4connector ucs2con sync of _msdcs DNS SRV record
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-s4-connector
##   - bind9-dnsutils

import subprocess

import univention.testing.strings as uts
from univention.testing import utils

import dnstests
import s4connector


if __name__ == '__main__':
    s4connector.exit_if_connector_not_running()

    print("========== Create DNS SRV record via univention-dnsedit ==========")
    s4_RR_val = uts.random_name()

    domainname = dnstests.ucr["domainname"]
    hostname = dnstests.ucr["hostname"]
    fqdn = f'{hostname}.{domainname}'
    location = "0 100 389 %s." % fqdn

    account = utils.UCSTestDomainAdminCredentials()

    cmd = ['/usr/share/univention-directory-manager-tools/univention-dnsedit', '--binddn=%s' % (account.binddn,), '--bindpwd=%s' % (account.bindpw,), '--ignore-exists', domainname, 'add', 'srv', s4_RR_val, 'msdcs', *location.split(' ')]
    print(" ".join(cmd))
    p = subprocess.Popen(cmd)
    p.wait()
    if p.returncode:
        print("WARNING: command exited with non-zero return code:\n%s" % (" ".join(cmd),))
    forward_zone_dn = "zoneName=%s,cn=dns,%s" % (domainname, dnstests.ucr["ldap/base"])

    test_relativeDomainName = "_%s._msdcs" % s4_RR_val
    test_srv_record_dn = "relativeDomainName=%s,%s" % (test_relativeDomainName, forward_zone_dn)
    test_fqdn = f'{test_relativeDomainName}.{domainname}'

    dnstests.check_ldap_object(test_srv_record_dn, 'Service Record', 'sRVRecord', location)
    s4connector.wait_for_sync(30)
    dnstests.test_dns_service_record(test_fqdn, location)
    dnstests.check_ldap_object(test_srv_record_dn, 'Modified Service Record', 'sRVRecord', location)

    dnstests.udm_remove_dns_record_object('dns/srv_record', test_srv_record_dn)
    utils.verify_ldap_object(test_srv_record_dn, should_exist=False)
    s4connector.wait_for_sync()
    dnstests.test_dns_service_record(test_fqdn, ".*", should_exist=False)
