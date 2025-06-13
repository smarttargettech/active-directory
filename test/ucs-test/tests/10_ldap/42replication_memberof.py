#!/usr/share/ucs-test/runner pytest-3 -s
## desc: memberOf replication tests
## tags:
##  - replication
##  - apptest
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages:
##  - univention-config
##  - univention-directory-manager-tools
##  - ldap-utils
## bugs:
##  - 46590
## exposure: dangerous

"""
The test checks, if the memberOf attribute is correctly set in all known test cases.
On DC Backup + DC Slave systems, there were missing memberOf values at user objects
if the listener was offline for some time OR there was a racing condition.

The test script runs through several scenarios (a test function for each scenario)
and tests with with_listener=False to trigger the racing condition (see bug #46590
for details) and with with_listener=True to make sure, that the usual scenario is
not affected.

Due to the inability of the S4 connector to handle group changes in diff mode
and the ucs-test framework to wait on all systems until all sync steps are done, the
test will be skipped for now on all system with samba4 installed but deactivated s4-connector.
Otherwise the test would be flaky.
"""
from __future__ import annotations

import pytest

from univention.config_registry import ucr
from univention.lib.misc import custom_groupname
from univention.testing import utils
from univention.testing.strings import random_name
from univention.testing.utils import start_listener, stop_listener, wait_for_replication


RETRY_COUNT = 20
DELAY = 6


class AutoStartStopListener:
    """Stops and starts listener automatically"""

    def __init__(self, dry_run: bool) -> None:
        """
        The listener is only shut down on __enter__ resp. started on __exit__, if dry_run != True.
        >>> with AutoStartStopListener(True):
        >>>     print('Do something with running listener')
        >>> with AutoStartStopListener(True):
        >>>     print('Do something with stopped listener')
        """
        self.dry_run = dry_run

    def __enter__(self):
        if not self.dry_run:
            stop_listener()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if not self.dry_run:
            start_listener()
            wait_for_replication()


@pytest.mark.skipif(
    utils.package_installed('univention-samba4') and ucr.is_false('connector/s4/autostart', False),
    reason='univention-samba4 is installed but no running S4 connector on this machine ',
)
class TestCases:
    base_user = 'cn=users,%(ldap/base)s' % ucr
    base_group = 'cn=groups,%(ldap/base)s' % ucr
    dn_domain_users = 'cn=%s,%s' % (custom_groupname('Domain Users', ucr), base_group)

    def print_attributes(self, udm, dn_list: list[str], msg: str | None = None) -> None:
        """
        Prints the DN and the values of the attributes memberOf and uniqueMember for all given
        DNs in dn_list. If msg is specified, a small header line is printed.
        """
        ATTR_LIST = ['memberOf', 'uniqueMember']
        print()
        if msg is not None:
            print('*** %s ***' % (msg,))
        for dn in dn_list:
            print(dn)
            attrs = udm._lo.get(dn, attr=ATTR_LIST)
            for key in ATTR_LIST:
                for val in attrs.get(key, []):
                    print('  %s: %s' % (key, val.decode('UTF-8')))
            print()

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_user_then_group(self, with_listener: bool, udm) -> None:
        """
        1) create user1
        2) create user2
        3) add user1 to group
        4) add user2 to group
        """
        with AutoStartStopListener(with_listener):
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1], wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener)

        self.print_attributes(udm, [dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(dn_grp1, {'uniqueMember': [dn_user1, dn_user2]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user1, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_user_group_mixed(self, with_listener: bool, udm) -> None:
        """
        1) create user1
        2) add user1 to group
        3) create user2
        4) add user2 to group
        """
        with AutoStartStopListener(with_listener):
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1], wait_for_replication=with_listener)
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener)

        self.print_attributes(udm, [dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(dn_grp1, {'uniqueMember': [dn_user1, dn_user2]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user1, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_move_user(self, with_listener: bool, udm) -> None:
        """
        1) create container
        2) create grp1
        3) create user1
        4) create user2
        5) add user1+user2 to group
        6) move user1 to new container
        """
        with AutoStartStopListener(with_listener):
            dn_cn = udm.create_object('container/cn', position=self.base_user, name=random_name(), wait_for_replication=with_listener)
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener)
            new_dn_user1 = udm.move_object('users/user', dn=dn_user1, position=dn_cn, wait_for_replication=with_listener)

        self.print_attributes(udm, [new_dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(dn_grp1, {'uniqueMember': [new_dn_user1, dn_user2]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(new_dn_user1, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_move_group(self, with_listener: bool, udm) -> None:
        """
        1) create container
        2) create grp1
        3) create user1
        4) create user2
        5) add user1+user2 to group
        6) move grp1 to new container
        """
        with AutoStartStopListener(with_listener):
            dn_cn = udm.create_object('container/cn', position=self.base_group, name=random_name(), wait_for_replication=with_listener)
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener)
            new_dn_grp1 = udm.move_object('groups/group', dn=dn_grp1, position=dn_cn, wait_for_replication=with_listener)

        self.print_attributes(udm, [dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(new_dn_grp1, {'uniqueMember': [dn_user1, dn_user2]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user1, {'memberOf': [new_dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [new_dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_rename_group(self, with_listener: bool, udm) -> None:
        """
        1) create grp1
        2) create user1
        3) create user2
        4) add user1+user2 to group
        5) rename grp1
        """
        with AutoStartStopListener(with_listener):
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener, wait_for=with_listener)
            new_dn_grp1 = udm.modify_object('groups/group', dn=dn_grp1, name=random_name(), wait_for_replication=with_listener, wait_for=with_listener)

        self.print_attributes(udm, [dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(new_dn_grp1, {'uniqueMember': [dn_user1, dn_user2]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user1, {'memberOf': [new_dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [new_dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_remove_group(self, with_listener: bool, udm) -> None:
        """
        1) create grp1
        2) create user1
        3) add user1 to group
        4) wait for replication
        5) create user2
        6) add user2 to group
        7) remove grp1
        """
        with AutoStartStopListener(with_listener):
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1], wait_for_replication=with_listener, wait_for=with_listener)

        with AutoStartStopListener(with_listener):
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener, wait_for=with_listener)
            udm.remove_object('groups/group', dn=dn_grp1, wait_for_replication=with_listener)

        udm.wait_for('groups/group', dn_grp1, wait_for_s4connector=with_listener)
        self.print_attributes(udm, [dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(dn_user1, {'memberOf': [self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

    @pytest.mark.parametrize("with_listener", [True, False])
    def test_remove_user_from_group(self, with_listener: bool, udm) -> None:
        """
        1) create grp1
        2) create user1
        3) add user1 to group
        4) wait for replication
        5) create user2
        6) add user2 to group
        7) remove user1 from group
        """
        with AutoStartStopListener(with_listener):
            dn_grp1 = udm.create_object('groups/group', position=self.base_group, name=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            dn_user1 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1], wait_for_replication=with_listener, wait_for=with_listener)

        wait_for_replication()
        with AutoStartStopListener(with_listener):
            dn_user2 = udm.create_object('users/user', position=self.base_user, username=random_name(), lastname=random_name(), password=random_name(), wait_for_replication=with_listener, wait_for=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, users=[dn_user1, dn_user2], wait_for_replication=with_listener, wait_for=with_listener)
            udm.modify_object('groups/group', dn=dn_grp1, remove={'users': [dn_user1]}, wait_for_replication=with_listener, wait_for=with_listener)

        wait_for_replication()
        self.print_attributes(udm, [dn_user1, dn_user2], 'RESULT')
        utils.verify_ldap_object(dn_grp1, {'uniqueMember': [dn_user2]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user1, {'memberOf': [self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)
        utils.verify_ldap_object(dn_user2, {'memberOf': [dn_grp1, self.dn_domain_users]}, strict=True, retry_count=RETRY_COUNT, delay=DELAY)

# vim: set ft=python :
