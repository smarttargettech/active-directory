#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Check for ucs/server/saml-idp-server/* variable
## tags: [saml]
## exposure: safe

from univention.testing.utils import fail, get_ldap_connection


def test_saml_idp_server(ucr):
    lo = get_ldap_connection()
    for res in lo.search('univentionService=univention-saml', attr=['cn', 'associatedDomain']):
        print(res[1])
        fqdn = b'%s.%s' % (res[1].get('cn')[0], res[1].get('associatedDomain')[0])
        fqdn = fqdn.decode('UTF-8')
        if ucr.get('ucs/server/saml-idp-server/%s' % fqdn) != fqdn:
            fail('ucs/server/saml-idp-server/%s is %s, expected %s' % (fqdn, ucr.get('ucs/server/saml-idp-server/%s' % fqdn), fqdn))
