#!/usr/share/ucs-test/runner python3
## desc: Fast add and delete an object, see if this creates an s4connector loop
## roles:
##  - domaincontroller_master
## packages:
##  - univention-s4-connector
##  - univention-directory-manager-tools
## bugs:
##  - 52358
## exposure: dangerous

import subprocess
import time

import univention.testing.udm as udm_test
from univention.config_registry import ConfigRegistry, handler_set as ucr_set
from univention.testing import strings
from univention.testing.utils import LDAPReplicationFailed, fail, wait_for_replication_and_postrun


ucr = ConfigRegistry()
ucr.load()


# create computer

object_names = []

udm = udm_test.UCSTestUDM()


def check_if_looping():
    try:
        wait_for_replication_and_postrun()
    except LDAPReplicationFailed:
        # stop loop
        print('ERROR: postrun never ran, ldap replication failed, most likely because of an s4con loop. Stopping the loop')
        ignorelist = ucr.get('connector/s4/mapping/windowscomputer/ignorelist', '')
        new_ignorelist = ignorelist + ','.join(object_names)
        ucr_set([f'connector/s4/mapping/windowscomputer/ignorelist={new_ignorelist}'])
        subprocess.check_call(["service", "univention-s4-connector", "restart"])
        print('Trying to wait for postrun again, see if a loop was the reason for failure')
        # wait a bit for things to settle..
        time.sleep(5)
        try:
            wait_for_replication_and_postrun()
        except LDAPReplicationFailed:
            fail('Test failed likely to different reason than an s4con-loop')
        else:
            fail('Moving objects to s4 ignorelist helped, which means that the previous tests created a loop')


def create_and_delete_computer(rounds=20):
    for _i in range(rounds):
        computername = strings.random_string()
        memberserver = udm.create_object(
            'computers/memberserver', name=computername,
            position='cn=memberserver,cn=computers,%s' % ucr.get('ldap/base'),
        )
        memberserver = udm.move_object(
            'computers/memberserver', dn=memberserver,
            position='cn=computers,%s' % ucr.get('ldap/base'),
        )
        udm.remove_object('computers/memberserver', dn=memberserver)
        object_names.append(computername)
    check_if_looping()


def main():
    create_and_delete_computer()


if __name__ == '__main__':
    main()
# vim: set ft=python :
