#!/usr/share/ucs-test/runner python3
## desc: ldapmodrdn / udm move replication tests
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
##  - 33495
## exposure: dangerous

import sys

import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.strings import random_name
from univention.testing.utils import start_listener, stop_listener, wait_for_replication


if __name__ == '__main__':
    if utils.package_installed('univention-samba4'):
        sys.exit(138)


def _get_name_normal():
    return random_name()


def _get_name_case_mix():
    return 'A' + random_name()


def _get_name_with_space():
    return 'A ' + random_name()


def _get_name_with_umlauts():
    return 'Aü ' + random_name()


def _get_ou_name():
    return random_name()


UDM_MODULE = 'computers/linux'

names = []
names.append(_get_name_normal())
names.append(_get_name_case_mix())
# Depends on the UDM_MODULE syntax
# names.append(_get_name_with_space())
# names.append(_get_name_with_umlauts())

source_ou_name = _get_ou_name()
destination_ou1_name = _get_ou_name()
destination_ou2_name = _get_ou_name()
destination_ou3_name = _get_ou_name()

udm = udm_test.UCSTestUDM()
source_ou = udm.create_object('container/ou', name=source_ou_name)
destination_ou1 = udm.create_object('container/ou', name=destination_ou1_name)
destination_ou2 = udm.create_object('container/ou', name=destination_ou2_name)
destination_ou3 = udm.create_object('container/ou', name=destination_ou3_name)
wait_for_replication()


def check_listener_stop(consider_listener):
    if consider_listener:
        stop_listener()


def check_listener_start(consider_listener):
    if consider_listener:
        start_listener()


def dump_status(consider_listener, wait_after_each_step, name):
    print('Consider listener: %s' % consider_listener)
    print('Wait for replication after each step: %s' % wait_after_each_step)
    print('Computer name: %s\n' % name)


for consider_listener in [False, True]:
    for wait_after_each_step in [False, True]:
        # wait is not possible if the listener should be not running
        if wait_after_each_step and consider_listener:
            continue

        for computer_name in names:
            check_listener_stop(consider_listener)
            name = computer_name + random_name(4)  # make name uniq
            print('\n***** Move once *****')
            dump_status(consider_listener, wait_after_each_step, name)
            computer = udm.create_object(UDM_MODULE, name=name, position=source_ou, wait_for_replication=wait_after_each_step)
            computer_new = udm.move_object(UDM_MODULE, dn=computer, position=destination_ou1, wait_for_replication=wait_after_each_step)
            check_listener_start(consider_listener)
            wait_for_replication()
            utils.verify_ldap_object(computer_new)
            utils.verify_ldap_object(computer, should_exist=False)

            check_listener_stop(consider_listener)
            name = computer_name + random_name(4)  # make name uniq
            print('\n***** Move twice *****')
            dump_status(consider_listener, wait_after_each_step, name)
            computer = udm.create_object(UDM_MODULE, name=name, position=source_ou, wait_for_replication=wait_after_each_step)
            udm.move_object(UDM_MODULE, dn=computer, position=destination_ou1, wait_for_replication=wait_after_each_step)
            computer_new = f'cn={name},{destination_ou1}'
            udm.move_object(UDM_MODULE, dn=computer_new, position=destination_ou2, wait_for_replication=wait_after_each_step)
            computer_new2 = f'cn={name},{destination_ou2}'
            check_listener_start(consider_listener)
            wait_for_replication()
            utils.verify_ldap_object(computer, should_exist=False)
            utils.verify_ldap_object(computer_new, should_exist=False)
            utils.verify_ldap_object(computer_new2)

            check_listener_stop(consider_listener)
            name = computer_name + random_name(4)  # make name uniq
            print('\n***** Move thrice *****')
            dump_status(consider_listener, wait_after_each_step, name)
            computer = udm.create_object(UDM_MODULE, name=name, position=source_ou, wait_for_replication=wait_after_each_step)
            udm.move_object(UDM_MODULE, dn=computer, position=destination_ou1, wait_for_replication=wait_after_each_step)
            computer_new = f'cn={name},{destination_ou1}'
            udm.move_object(UDM_MODULE, dn=computer_new, position=destination_ou2, wait_for_replication=wait_after_each_step)
            computer_new2 = f'cn={name},{destination_ou2}'
            udm.move_object(UDM_MODULE, dn=computer_new2, position=destination_ou3, wait_for_replication=wait_after_each_step)
            computer_new3 = f'cn={name},{destination_ou3}'
            check_listener_start(consider_listener)
            wait_for_replication()
            utils.verify_ldap_object(computer, should_exist=False)
            utils.verify_ldap_object(computer_new, should_exist=False)
            utils.verify_ldap_object(computer_new2, should_exist=False)
            if not consider_listener:
                # this will be failed cause of https://forge.univention.org/bugzilla/show_bug.cgi?id=32206
                utils.verify_ldap_object(computer_new3)

            # create and delete target before starting
            print('\n***** Create delete and move once *****')
            name = computer_name + random_name(4)  # make name uniq
            dump_status(consider_listener, wait_after_each_step, name)
            computer = udm.create_object(UDM_MODULE, name=name, position=destination_ou1, wait_for_replication=True)
            udm.remove_object(UDM_MODULE, dn=computer, wait_for_replication=True)
            check_listener_stop(consider_listener)
            computer = udm.create_object(UDM_MODULE, name=name, position=source_ou, wait_for_replication=wait_after_each_step)
            udm.move_object(UDM_MODULE, dn=computer, position=destination_ou1, wait_for_replication=wait_after_each_step)
            computer_new = f'cn={name},{destination_ou1}'
            check_listener_start(consider_listener)
            wait_for_replication()
            if not consider_listener:
                # this will be failed cause of https://forge.univention.org/bugzilla/show_bug.cgi?id=32206
                utils.verify_ldap_object(computer_new)
            utils.verify_ldap_object(computer, should_exist=False)


udm.cleanup()
wait_for_replication()

# vim: set ft=python :
