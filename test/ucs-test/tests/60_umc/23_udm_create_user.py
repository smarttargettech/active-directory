#!/usr/share/ucs-test/runner python3
## desc: Test the UMC user creation, modification and deletion
## bugs: [34791]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## tags: [skip_admember]
## exposure: dangerous

import sys

from univention.testing import utils
from univention.testing.strings import random_username

from umc import UDMModule


class TestUMCUserCreation(UDMModule):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()
        self.ldap_base = None

    def get_user_by_uid(self, uid):
        """Returns the 'uid' user data obtained by 'udm/get' UMC request."""
        options = ["uid=" + uid + ",cn=users," + self.ldap_base]
        request_result = self.client.umc_command('udm/get', options, 'users/user').result
        if not request_result:
            utils.fail(f"Request 'udm/get' with options '{options}' failed, hostname '{self.hostname}'")
        return request_result

    def modify_user_groups(self, username, groupnames):
        """
        Modifies a user group with provided 'username' and a list of
        'groupnames' via UMC 'udm/put' request.
        """
        options = [{
            "object": {
                "groups": groupnames,
                "$dn$": "uid=" + username + ",cn=users," + self.ldap_base,
            },
            "options": {
                "objectType": "users/user",
            },
        }]
        request_result = self.client.umc_command('udm/put', options, 'users/user').result
        if not request_result:
            utils.fail(f"Request 'udm/put' to change user '{username}' groups with options '{options}' failed, hostname {self.hostname}")
        if not request_result[0].get('success'):
            utils.fail(f"Request 'udm/put' to change user '{username}' groups with options '{options}' failed, no success = True in response, hostname {self.hostname}")

    def create_user(self, username, password, groupname,
                    group_container="groups"):
        """
        Creates a test user by making a UMC-request 'udm/add'
        with provided 'username', 'password' and the 'groupname'
        as a primary group.
        """
        options = [{
            "object": {
                "disabled": "0",
                "lastname": username,
                "password": password,
                "overridePWHistory": False,
                "pwdChangeNextLogin": False,
                "primaryGroup": "cn=" + groupname + ",cn=" + group_container + "," + self.ldap_base,
                "username": username,
                "shell": "/bin/bash",
                "locked": "0",
                "homeSharePath": username,
                "unixhome": "/home/" + username,
                "overridePWLength": False,
                "displayName": username,
                "$options$": {
                    "person": True,
                    "mail": True,
                    "pki": False,
                },
            },
            "options": {
                "container": "cn=users," + self.ldap_base,
                "objectType": "users/user",
            },
        }]
        try:
            request_result = self.client.umc_command('udm/add', options, 'users/user').result
            if not request_result:
                utils.fail("Request 'udm/add' user failed. Response: %r\nRequest options: %r\n"
                           "hostname: %r" % (request_result, options, self.hostname))
            if not request_result[0].get('success'):
                utils.fail("Request 'udm/add' user not successful. Response: %r\nRequest options: %r\n"
                           "hostname %r" % (request_result, options, self.hostname))
        except Exception as exc:
            utils.fail("Exception while making 'udm/add' user request: %s" %
                       exc)

    def main(self):
        """Method to test UMC users creation, modification and deletion"""
        self.create_connection_authenticate()
        self.ldap_base = self.ucr.get('ldap/base')

        test_username = 'umc_test_user_' + random_username(6)
        test_username_admin = test_username + '_admin'
        test_password = 'Univention@99'

        # get localized groups translations if any:
        domain_users = self.get_groupname_translation('domainusers')
        domain_admins = self.get_groupname_translation('domainadmins')
        print_admins = self.get_groupname_translation('printoperators')

        try:
            print("Creating a simple domain user with username '%s'"
                  % test_username)
            self.create_user(test_username, test_password, domain_users)
            if not self.check_obj_exists(test_username, "users/user", "users/user"):
                utils.fail("Cannot query a simple test user '%s' that "
                           "was just created" % test_username)

            print("Creating an advanced user (Administrator) with username "
                  "'%s'" % test_username_admin)
            self.create_user(test_username_admin, test_password,
                             domain_admins)
            if not self.check_obj_exists(test_username_admin, "users/user", "users/user"):
                utils.fail("Cannot query an advanced test user '%s' that "
                           "was just created" % test_username_admin)

            print("Modifying simple user '%s' groups" % test_username)
            test_groupnames = ["cn=" + domain_users + ",cn=groups," + self.ldap_base, "cn=" + print_admins + ",cn=groups," + self.ldap_base]
            self.modify_user_groups(test_username, test_groupnames)

            print("Checking simple user '%s' groups" % test_username)
            user_groups = self.get_user_by_uid(test_username)[0].get('groups')
            if not user_groups:
                utils.fail("No groups or empty groups in response for user "
                           "'%s'" % test_username)
            if set(user_groups) != set(test_groupnames):
                utils.fail("The '%s' user is in the wrong group(s) '%s', "
                           "while should be only in '%s'"
                           % (test_username, user_groups, test_groupnames))

            print("Modifying advanced user '%s' groups" % test_username_admin)
            test_groupnames = ["cn=" + domain_admins + ",cn=groups," + self.ldap_base, "cn=" + print_admins + ",cn=groups," + self.ldap_base]
            self.modify_user_groups(test_username_admin, test_groupnames)

            print("Checking advanced user '%s' groups" % test_username_admin)
            user_groups = self.get_user_by_uid(test_username_admin)[0].get(
                'groups')
            if not user_groups:
                utils.fail("No groups or empty groups in response for user "
                           "'%s'" % test_username_admin)
            if set(user_groups) != set(test_groupnames):
                utils.fail("The '%s' user is in the wrong group(s) '%s', "
                           "while should be only in '%s'"
                           % (test_username_admin,
                              user_groups,
                              test_groupnames))
        finally:
            print("Removing created test users if any")
            if self.check_obj_exists(test_username, "users/user", "users/user"):
                self.delete_obj(test_username, "users/user", "users/user")
            if self.check_obj_exists(test_username_admin, "users/user", "users/user"):
                self.delete_obj(test_username_admin, "users/user", "users/user")


if __name__ == '__main__':
    TestUMC = TestUMCUserCreation()
    sys.exit(TestUMC.main())
