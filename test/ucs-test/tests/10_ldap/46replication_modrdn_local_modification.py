#!/usr/share/ucs-test/runner python3
## desc: Move an UDM computers object to a position which already exists local as container
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

import os
import re
import sys

import ldap

import univention.testing.udm as udm_test
import univention.uldap
from univention.config_registry import ConfigRegistry
from univention.testing.strings import random_name
from univention.testing.utils import wait_for_replication


success = True

ucr = ConfigRegistry()
ucr.load()

UDM_MODULE = 'computers/linux'

name = random_name()
dn = 'cn=%s,cn=memberserver,cn=computers,%s' % (name, ucr.get('ldap/base'))
addlist = [
    ('cn', [name.encode('UTF-8')]),
    ('objectClass', [b'top', b'organizationalRole', b'univentionObject']),
    ('univentionObjectType', [b'container/cn']),
]

name_subobject = random_name()
dn_subobject = 'cn=%s,cn=%s,cn=memberserver,cn=computers,%s' % (name_subobject, name, ucr.get('ldap/base'))
addlist_subobject = [
    ('cn', [name_subobject.encode('UTF-8')]),
    ('objectClass', [b'top', b'organizationalRole', b'univentionObject']),
    ('univentionObjectType', [b'container/cn']),
]


def get_entryUUID(lo, dn):
    result = lo.search_s(base=dn, scope=ldap.SCOPE_BASE, attrlist=['entryUUID'])
    print('DN: %s\n%s' % (dn, result))
    return result[0][1].get('entryUUID')[0].decode('ASCII')

# create computer


udm = udm_test.UCSTestUDM()
computer = udm.create_object(UDM_MODULE, name=name, position=ucr.get('ldap/base'), wait_for_replication=True)

lo = univention.uldap.getRootDnConnection().lo

# read computer uuid
computer_UUID = get_entryUUID(lo, computer)

# create container
lo.add_s(dn, addlist)
lo.add_s(dn_subobject, addlist_subobject)

container_UUID = get_entryUUID(lo, dn)
subcontainer_UUID = get_entryUUID(lo, dn_subobject)

# move container to the same position of the new container
udm.move_object(UDM_MODULE, dn=computer, position='cn=memberserver,cn=computers,%s' % ucr.get('ldap/base'), wait_for_replication=True)

new_computer_UUID = get_entryUUID(lo, dn)

# The container should have be replaced by the computer object
if computer_UUID != new_computer_UUID:
    print('ERROR: entryUUID of moved object do not match')
    print('  new_computer_UUID: %s' % computer_UUID)
    print('      computer_UUID: %s' % new_computer_UUID)
    print('     container_UUID: %s' % container_UUID)
    success = False

found_backup_container = False
found_backup_subcontainer = False

BACKUP_DIR = '/var/univention-backup/replication'
if os.path.exists(BACKUP_DIR):
    for f in os.listdir(BACKUP_DIR):
        fd = open(os.path.join(BACKUP_DIR, f))
        for line in fd.readlines():
            if re.match('entryUUID: %s' % container_UUID, line):
                found_backup_container = True
            elif re.match('entryUUID: %s' % subcontainer_UUID, line):
                found_backup_subcontainer = True
        fd.close()

if not found_backup_container:
    print('ERROR: Backup of container with UUID %s was not found' % container_UUID)
    success = False
if not found_backup_subcontainer:
    print('ERROR: Backup of subcontainer with UUID %s was not found' % subcontainer_UUID)
    success = False


udm.cleanup()
wait_for_replication()

if not success:
    sys.exit(1)

# vim: set ft=python :
