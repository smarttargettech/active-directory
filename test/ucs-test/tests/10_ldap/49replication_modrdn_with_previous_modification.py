#!/usr/share/ucs-test/runner python3
## desc: Modify and move an object while the listener is stopped
## tags:
##  - replication
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages:
##  - univention-config
##  - univention-directory-manager-tools
##  - ldap-utils
## bugs:
##  - 34355
## exposure: dangerous

import os
import sys

import ldap

import univention.testing.udm as udm_test
from univention import uldap
from univention.config_registry import ConfigRegistry
from univention.testing.strings import random_name
from univention.testing.utils import restart_listener, start_listener, stop_listener, wait_for_replication


success = True

ucr = ConfigRegistry()
ucr.load()


def get_entryUUID(lo, dn):
    result = lo.search(base=dn, scope=ldap.SCOPE_BASE, attr=['*', '+'])
    print(f'DN: {dn}\n{result}')
    return result[0][1].get('entryUUID')[0]


def create_listener_module_for_computer(computer_name):
    filename = '/usr/lib/univention-directory-listener/system/%s-test.py' % (computer_name)
    fd = open(filename, 'w')
    fd.write('''
from __future__ import absolute_import

from typing import Dict, List

import univention.debug as ud

modrdn = "1"
name="%(computer_name)s-test"
description="%(computer_name)s"
filter="(cn=%(computer_name)s)"

def handler(dn: str, new: Dict[str, List[bytes]], old: Dict[str, List[bytes]], command: str) -> None:
    if command == 'r':
        return
    ud.debug(ud.LISTENER, ud.PROCESS, "ucs-test debug: dn: %%s" %% dn)
    ud.debug(ud.LISTENER, ud.PROCESS, "ucs-test debug: old: %%s" %% old)
    ud.debug(ud.LISTENER, ud.PROCESS, "ucs-test debug: new: %%s" %% new)
    if old and not new:
        fd = open('/tmp/%(computer_name)s-test', 'w')
''' % {'computer_name': computer_name})
    restart_listener()


def remove_listener_module_for_computer(computer_name):
    filename = '/usr/lib/univention-directory-listener/system/%s-test.py' % (computer_name)
    if os.path.exists(filename):
        os.remove(filename)
    restart_listener()

# create computer


udm = udm_test.UCSTestUDM()

container_name = random_name()
computer_name = random_name()

create_listener_module_for_computer(computer_name)

position = 'cn=memberserver,cn=computers,%s' % (ucr.get('ldap/base'))
container = udm.create_object('container/cn', name=container_name, position=position, wait_for_replication=True)
computer = udm.create_object('computers/linux', name=computer_name, position=container, wait_for_replication=True)

lo = uldap.getMachineConnection()

# read computer uuid
computer_UUID = get_entryUUID(lo, computer)

# Stop listener
stop_listener()

udm.modify_object('computers/linux', dn=computer, description=computer_name, wait_for_replication=False)

# move container to the same position of the new container
new_computer_dn = f'cn={computer_name},{position}'
udm.move_object('computers/linux', dn=computer, position=position, wait_for_replication=False)

start_listener()

wait_for_replication()

new_computer_UUID = get_entryUUID(lo, new_computer_dn)

# The container should have be replaced by the computer object
if computer_UUID != new_computer_UUID:
    print('ERROR: entryUUID of moved object do not match')
    success = False

delete_handler_file = '/tmp/%s-test' % computer_name
if os.path.exists(delete_handler_file):
    print('ERROR: the delete handler was called for the modified and moved object')
    success = False
    os.remove(delete_handler_file)

remove_listener_module_for_computer(computer_name)
udm.cleanup()
wait_for_replication()

if not success:
    sys.exit(1)

# vim: set ft=python :
