#!/usr/share/ucs-test/runner python3
## desc: test automatic reconnect of uldap.py
## tags: [skip_admember,reconnect]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - python3-univention-directory-manager
##   - python3-univention

import subprocess

import ldap

import univention.uldap


lo = univention.uldap.getMachineConnection()
dn = lo.lo.whoami_s()[3:]
attrs = lo.get(dn)
print(('Attrs=', attrs))
subprocess.call(['service', 'slapd', 'stop'])
try:
    try:
        lo.get(dn)
    except ldap.SERVER_DOWN:
        print('LDAP server is down!')
    else:
        raise ValueError('did not raise SERVER_DOWN')

    subprocess.call(['service', 'slapd', 'start'])
    new_attrs = lo.get(dn)
    print(('New Attrs=', new_attrs))
    assert attrs == new_attrs
finally:
    subprocess.call(['service', 'slapd', 'restart'])
