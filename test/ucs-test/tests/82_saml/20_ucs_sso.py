#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Check if every DC Master and DC Backup is registered in ucs-sso
## tags: [saml]
## roles: [domaincontroller_master, domaincontroller_backup]
## exposure: safe

import dns.ipv6
import dns.resolver

from univention.testing.utils import fail, get_ldap_connection


def _check_record_type(record_type, ucr):
    print(f'Checking record type: {record_type}')
    dns_entries = set()
    sso_name = ucr.get('keycloak/server/sso/fqdn', f'ucs-sso-ng.{ucr["domainname"]}')
    try:
        dns_entries.update(addr.address for addr in dns.resolver.query(sso_name, record_type))
    except dns.resolver.NoAnswer:
        pass
    print('DNS entries: {}'.format('; '.join(dns_entries)))

    master_backup_ips = set()
    lo = get_ldap_connection()
    ldap_record_name = {'A': 'aRecord', 'AAAA': 'aAAARecord'}
    ldap_filter = '(&(|(univentionServerRole=master)(univentionServerRole=backup))(univentionService=keycloak))'
    for res in lo.search(ldap_filter, attr=[ldap_record_name[record_type]]):
        if res[1]:
            for ip in res[1].get(ldap_record_name[record_type]):
                if record_type == 'AAAA':
                    ip = dns.ipv6.inet_ntoa(dns.ipv6.inet_aton(ip))
                master_backup_ips.add(ip.decode('ASCII'))
    print('LDAP entries: {}'.format('; '.join(master_backup_ips)))

    if master_backup_ips.difference(dns_entries):
        fail('Not all master and backup IPs are registered: DNS: [%s], LDAP: [%s]' % (dns_entries, master_backup_ips))
    return len(dns_entries)


def test_ucs_sso_records(ucr):
    number_of_records = 0
    for record_type in ('A', 'AAAA'):
        number_of_records += _check_record_type(record_type, ucr)

    if number_of_records == 0:
        fail('No dns record for ucs-sso')
    print('Success')
