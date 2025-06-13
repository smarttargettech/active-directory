#!/usr/share/ucs-test/runner python3
## desc: test ldap constraints
## bugs: [43312]
## roles:
##  - domaincontroller_master
## packages:
##  - python3-univention-lib
##  - python3-ldap
## exposure: dangerous

import atexit
import ldap
import pytest

import univention.uldap
from univention.config_registry import ucr


def main():
    test_uidnumber_0()
    test_gidnumber_0()


def test_uidnumber_0():
    lo = univention.uldap.getAdminConnection()
    dn = 'cn=foo,%s' % ucr['ldap/base']
    cleanup.dns.append(dn)
    with pytest.raises(ldap.CONSTRAINT_VIOLATION) as msg:
        print('add', dn)
        lo.add(dn, [
            ('objectClass', b'', b'posixAccount'),
            ('objectClass', b'', b'organizationalRole'),
            ('cn', b'', b'foo'),
            ('uid', b'', b'foo'),
            ('homeDirectory', b'', b'/home/foo'),
            ('uidNumber', b'', b'0'),
            ('gidNumber', b'', b'1'),
        ])
    print(msg)
    assert msg.value.args[0]['info'] == 'add breaks constraint on uidNumber'


def test_gidnumber_0():
    lo = univention.uldap.getAdminConnection()
    dn = 'cn=bar,%s' % ucr['ldap/base']
    cleanup.dns.append(dn)
    with pytest.raises(ldap.CONSTRAINT_VIOLATION) as msg:
        print('add', dn)
        lo.add(dn, [
            ('objectClass', b'', b'posixAccount'),
            ('objectClass', b'', b'organizationalRole'),
            ('cn', b'', b'bar'),
            ('uid', b'', b'bar'),
            ('homeDirectory', b'', b'/home/bar'),
            ('uidNumber', b'', b'1'),
            ('gidNumber', b'', b'0'),
        ])
    print(msg)
    assert msg.value.args[0]['info'] == 'add breaks constraint on gidNumber'


def cleanup():
    lo = univention.uldap.getAdminConnection()
    for dn in cleanup.dns:
        lo.get(dn) and lo.delete(dn)


if __name__ == '__main__':
    atexit.register(cleanup)
    cleanup.dns = []
    main()
