#!/usr/share/ucs-test/runner python3
## desc: Move a computer which has in the local LDAP server a different entryUUID
## tags:
##  - replication
## roles:
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages:
##  - univention-config
##  - univention-directory-manager-tools
##  - ldap-utils
## bugs:
##  - 33495
## exposure: dangerous

import sys

import ldap

import univention.testing.udm as udm_test
import univention.uldap
from univention.config_registry import ConfigRegistry
from univention.testing import utils
from univention.testing.strings import random_name
from univention.testing.utils import wait_for_replication


success = True

ucr = ConfigRegistry()
ucr.load()

UDM_MODULE = 'computers/ipmanagedclient'

name = random_name()
dn = 'cn=%s,cn=memberserver,cn=computers,%s' % (name, ucr.get('ldap/base'))
modlist = [
    (ldap.MOD_REPLACE, 'entryUUID', b'76944348-ea2e-1032-95ad-000000000000'),
]


def get_entryUUID(lo, dn):
    result = lo.search_s(base=dn, scope=ldap.SCOPE_BASE, attrlist=['*', '+'])
    print('DN: %s\n%s' % (dn, result))
    return result[0][1].get('entryUUID')[0].decode('ASCII')


lo_local = univention.uldap.getRootDnConnection().lo
lo_remote = univention.uldap.getMachineConnection().lo

# create computer
udm = udm_test.UCSTestUDM()
computer = udm.create_object(UDM_MODULE, name=name, position='cn=memberserver,cn=computers,%s' % (ucr.get('ldap/base')), wait_for_replication=True)

# change entryUUID
lo_local.modify_s(dn, modlist)

local_UUID = get_entryUUID(lo_local, dn)
remote_UUID = get_entryUUID(lo_remote, dn)

# move computer
udm.move_object(UDM_MODULE, dn=computer, position='cn=computers,%s' % ucr.get('ldap/base'), wait_for_replication=True)
new_dn = 'cn=%s,cn=computers,%s' % (name, ucr.get('ldap/base'))

new_local_UUID = get_entryUUID(lo_local, new_dn)
new_remote_UUID = get_entryUUID(lo_remote, new_dn)

if new_local_UUID != new_remote_UUID:
    print('ERROR: local and remote UUID do not match')
    print('  local_UUID: %s' % new_local_UUID)
    print(' remote_UUID: %s' % new_remote_UUID)
    success = False

utils.verify_ldap_object(dn, should_exist=False)
utils.verify_ldap_object(new_dn, should_exist=True)

udm.cleanup()
wait_for_replication()

if not success:
    sys.exit(1)

# vim: set ft=python :
