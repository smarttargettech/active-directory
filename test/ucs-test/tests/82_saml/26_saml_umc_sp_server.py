#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Check for umc/saml/trusted/sp/* variable
## tags: [saml]
## exposure: safe
## bugs: [39552]

from univention.testing.utils import fail, get_ldap_connection


def test_saml_umc_sp_server(ucr):
    lo = get_ldap_connection()
    for res in lo.search('univentionService=Univention Management Console', attr=['cn', 'associatedDomain']):
        print(res[1])
        fqdn = b'%s.%s' % (res[1].get('cn')[0], res[1].get('associatedDomain')[0])
        fqdn = fqdn.decode('UTF-8')
        if ucr.get('umc/saml/trusted/sp/%s' % fqdn) != fqdn:
            fail('umc/saml/trusted/sp/%s is %s, expected %s' % (fqdn, ucr.get('umc/saml/trusted/sp/%s' % fqdn), fqdn))
